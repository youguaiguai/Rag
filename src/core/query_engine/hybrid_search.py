"""
HybridSearch — 混合检索引擎编排（Dense + Sparse + RRF Fusion + Metadata 过滤）

知识点：Hybrid Search 是 RAG 检索的核心编排层
  - 检索链路：Query → QueryProcessor → DenseRetriever + SparseRetriever → **HybridSearch** → Reranker
  - 职责：
    1. 调用 QueryProcessor 处理查询
    2. 并行执行 Dense 和 Sparse 检索
    3. 用 RRF Fusion 融合结果
    4. 应用 metadata 过滤
    5. 降级处理（任一路径失败 → 使用另一路径结果）
  - 面试考点："为什么需要 HybridSearch？" → 统一编排检索流程 + 降级策略

Hybrid Search 的两阶段架构（面试必问）：
  1. 粗排（HybridSearch）：Dense + Sparse + RRF → 返回 Top-K 候选
  2. 精排（Reranker）：对候选进行精排（CrossEncoder / LLM）
  - 面试考点："为什么不一步到位？" → 性能考虑，精排只对 Top-K 候选执行

降级策略设计（面试考点）：
  - Dense 失败 + Sparse 成功 → 返回 Sparse 结果（保证有结果）
  - Sparse 失败 + Dense 成功 → 返回 Dense 结果（保证有结果）
  - 两者都失败 → 抛异常（无法返回任何结果）
  - 面试考点："为什么不用异常？" → 单路失败不应阻塞整个检索流程

Metadata 过滤设计：
  - 前置过滤：filters 传递给 DenseRetriever（VectorStore 层过滤）
  - 后置过滤：_apply_metadata_filters() 在融合后再次过滤（兜底）
  - 面试考点："为什么有两个过滤阶段？" → VectorStore 过滤不完全可靠，后置过滤兜底

接口签名：
  HybridSearch(settings, query_processor, dense_retriever, sparse_retriever, fusion)
  search(query, top_k, filters?, trace?) -> list[RetrievalResult]
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from core.query_engine.query_processor import QueryProcessor
    from core.query_engine.dense_retriever import DenseRetriever
    from core.query_engine.sparse_retriever import SparseRetriever
    from core.query_engine.fusion import Fusion

logger = logging.getLogger(__name__)


class HybridSearch:
    """混合检索引擎 — 编排 Dense + Sparse + Fusion + Metadata 过滤

    知识点：HybridSearch 的设计原则
      - 编排层：不实现检索逻辑，只编排各组件协作
      - 降级处理：任一路径失败时自动降级到单路结果
      - 并行执行：Dense 和 Sparse 使用线程池并行执行（IO 密集型）
      - 面试考点："为什么不顺序执行？" → 并行节省等待时间（Dense embed + BM25 都是 IO/API 调用）

    接口签名：
      HybridSearch(settings, query_processor, dense_retriever, sparse_retriever, fusion)
      search(query, top_k=10, filters=None, trace=None) -> list[RetrievalResult]
      _apply_metadata_filters(candidates, filters) -> list[RetrievalResult]
    """

    def __init__(
        self,
        settings: Settings,
        query_processor: QueryProcessor,
        dense_retriever: DenseRetriever,
        sparse_retriever: SparseRetriever,
        fusion: Fusion,
    ) -> None:
        """初始化 HybridSearch

        接口签名：HybridSearch(settings, query_processor, dense_retriever, sparse_retriever, fusion)
        入参：
          - settings: 全局配置
          - query_processor: 查询预处理器
          - dense_retriever: 稠密检索器
          - sparse_retriever: 稀疏检索器
          - fusion: 结果融合器

        知识点：依赖注入（与 DenseRetriever/SparseRetriever 一致）
          - 所有组件通过构造函数注入
          - 上层负责创建和管理组件生命周期
        """
        self._settings = settings
        self._query_processor = query_processor
        self._dense_retriever = dense_retriever
        self._sparse_retriever = sparse_retriever
        self._fusion = fusion

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        trace: TraceContext | None = None,
    ) -> list[Any]:
        """混合检索 — Dense + Sparse + RRF Fusion + Metadata 过滤

        接口签名：search(query, top_k=10, filters=None, trace=None) -> list[RetrievalResult]
        入参：
          - query: 用户查询字符串
          - top_k: 最终返回的 Top-K 结果数量
          - filters: 可选的 metadata 过滤条件
          - trace: 可选的追踪上下文
        出参：RetrievalResult 列表，按 RRF score 降序排列

        内部流程：
          1. query_processor.process(query, filters) → ProcessedQuery
          2. 并行执行：
             - dense_retriever.retrieve(raw_query, top_k_retrieval, filters)
             - sparse_retriever.retrieve(keywords, top_k_retrieval)
          3. 降级处理（任一路径失败 → 使用另一路径结果）
          4. fusion.fuse([dense_results, sparse_results]) → 融合结果
          5. _apply_metadata_filters(merged, filters) → 后置过滤
          6. 返回 Top-K

        面试考点：
          "HybridSearch 的完整流程？" → process → parallel retrieve → fuse → filter → Top-K
          "Dense 和 Sparse 的 top_k 为什么比最终 top_k 大？" → 留余量给融合（有些结果可能重复）

        降级策略：
          - 最优：Dense + Sparse 都成功 → Fusion 融合
          - 次优：只有 Dense 成功 → 返回 Dense 结果
          - 次优：只有 Sparse 成功 → 返回 Sparse 结果
          - 最差：两者都失败 → 抛异常
        """
        import time

        from core.query_engine.query_processor import QueryProcessor

        start = time.perf_counter()

        # 1. 查询预处理（带降级）
        try:
            processed = self._query_processor.process(query, filters=filters, trace=trace)
        except ValueError:
            # query 为空 — 直接返回空结果
            logger.warning("HybridSearch: 查询为空，返回空结果")
            return []

        raw_query = processed.raw_query
        keywords = processed.keywords

        # 检索用的 top_k（比最终 top_k 大，留余量给融合去重和过滤）
        retrieval_top_k = self._settings.retrieval.top_k_dense

        # 2. 并行执行 Dense + Sparse 检索
        dense_results: list[Any] = []
        sparse_results: list[Any] = []
        dense_error: Exception | None = None
        sparse_error: Exception | None = None

        def _run_dense() -> list[Any]:
            return self._dense_retriever.retrieve(
                query=raw_query,
                top_k=retrieval_top_k,
                filters=filters,
            )

        def _run_sparse() -> list[Any]:
            return self._sparse_retriever.retrieve(
                keywords=keywords,
                top_k=retrieval_top_k,
            )

        # 使用线程池并行执行
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_dense = executor.submit(_run_dense)
            future_sparse = executor.submit(_run_sparse)

            try:
                dense_results = future_dense.result(timeout=30)
            except Exception as e:
                dense_error = e
                logger.warning("Dense 检索失败（降级到 Sparse）: %s", e)

            try:
                sparse_results = future_sparse.result(timeout=30)
            except Exception as e:
                sparse_error = e
                logger.warning("Sparse 检索失败（降级到 Dense）: %s", e)

        # 3. 降级处理
        if dense_error and sparse_error:
            # 两者都失败 — 无法返回任何结果
            total_ms = (time.perf_counter() - start) * 1000
            if trace is not None:
                trace.record_stage(
                    "hybrid_search",
                    {"status": "both_failed"},
                    duration_ms=round(total_ms, 2),
                )
            raise RuntimeError(
                f"混合检索失败：Dense 和 Sparse 都失败\n"
                f"Dense 错误: {dense_error}\n"
                f"Sparse 错误: {sparse_error}"
            )

        if dense_error and not sparse_error:
            # Dense 失败 → 返回 Sparse 结果
            merged = sparse_results
            mode = "sparse_only"
        elif sparse_error and not dense_error:
            # Sparse 失败 → 返回 Dense 结果
            merged = dense_results
            mode = "dense_only"
        else:
            # 两者都成功 → RRF Fusion 融合
            merged = self._fusion.fuse(
                [dense_results, sparse_results],
                top_k=None,  # 不在融合阶段截断，留给后置 Top-K
            )
            mode = "fused"

        # 4. Metadata 后置过滤
        if filters:
            merged = self._apply_metadata_filters(merged, filters)

        # 5. Top-K 截断
        final_results = merged[:top_k]

        # 6. 记录 trace
        total_ms = (time.perf_counter() - start) * 1000
        if trace is not None:
            trace.record_stage(
                "hybrid_search",
                {
                    "query": raw_query[:200],
                    "mode": mode,
                    "keywords_count": len(keywords),
                    "dense_count": len(dense_results),
                    "sparse_count": len(sparse_results),
                    "fused_count": len(merged),
                    "final_count": len(final_results),
                },
                duration_ms=round(total_ms, 2),
            )

        logger.debug(
            "HybridSearch: query=%r → mode=%s → %d results (%.1fms)",
            raw_query[:100],
            mode,
            len(final_results),
            total_ms,
        )

        return final_results

    def _apply_metadata_filters(
        self,
        candidates: list[Any],
        filters: dict[str, Any],
    ) -> list[Any]:
        """后置 metadata 过滤 — 兜底过滤

        接口签名：_apply_metadata_filters(candidates, filters) -> list[RetrievalResult]
        入参：
          - candidates: 融合后的候选结果列表
          - filters: metadata 过滤条件
        出参：过滤后的结果列表

        知识点：后置过滤的作用
          - VectorStore 的前置过滤可能不完全可靠（backend 实现差异）
          - 后置过滤是 Java 风格的"契约式编程"：不信任上游，自己兜底
          - 面试考点："为什么有两个过滤阶段？" → 前置过滤提升性能，后置过滤保证正确性

        过滤逻辑：
          - filters 中的每个 key-value 对都必须在 result.metadata 中精确匹配
          - 相当于 AND 逻辑
          - 面试考点："支持 OR 逻辑吗？" → 当前只支持 AND，复杂过滤需扩展

        注意：
          - filters 可能包含特殊字段如 "collection"、"doc_type"、"source" 等
          - 匹配是精确匹配（==），不支持模糊匹配
        """
        if not filters:
            return candidates

        filtered: list[Any] = []
        for result in candidates:
            # 检查是否所有 filter 条件都满足
            match = all(
                result.metadata.get(k) == v
                for k, v in filters.items()
            )
            if match:
                filtered.append(result)

        if len(filtered) < len(candidates):
            logger.debug(
                "Metadata 过滤: %d → %d (过滤掉 %d 条)",
                len(candidates),
                len(filtered),
                len(candidates) - len(filtered),
            )

        return filtered

