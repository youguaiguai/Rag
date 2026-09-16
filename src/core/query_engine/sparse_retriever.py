"""
SparseRetriever — BM25 关键词检索

知识点：SparseRetriever 在 RAG 检索链路中的位置
  - 检索链路：Query → QueryProcessor → DenseRetriever + SparseRetriever → Fusion → Reranker
  - 职责：将关键词 → BM25 索引查询 → VectorStore 获取原文 → 返回 RetrievalResult 列表
  - 与 DenseRetriever 互补：Sparse 捕获精确匹配，Dense 捕获语义相似性

SparseRetriever 的核心流程（面试考点）：
  1. keywords → bm25_indexer.query(keywords, top_k) → [{chunk_id, score}]
  2. chunk_ids → vector_store.get_by_ids(chunk_ids) → [{id, text, metadata}]
  3. 合并 score 与 text/metadata，组装为 RetrievalResult 列表
  - 面试考点："为什么 SparseRetriever 需要 VectorStore？" → BM25 只存 ID+分数，原文在 VectorStore

BM25 查询的特点（面试考点）：
  - 只返回包含查询词的文档（倒排索引特性）
  - 不含查询词的文档不会被召回（与 Dense 的本质区别）
  - 面试考点："Dense 和 Sparse 召回结果有什么差异？" →
    Dense 返回语义相似但不一定含相同词的文档；Sparse 返回含相同词但可能语义不同的文档

依赖注入设计（与 DenseRetriever 一致）：
  - __init__(settings, bm25_indexer?, vector_store?)
  - bm25_indexer 和 vector_store 可选注入，用于测试隔离
  - 不注入时从 settings 自动创建（生产环境）

降级策略：
  - SparseRetriever 失败直接抛异常（Fail-Fast）
  - HybridSearch 层负责降级（Sparse 失败 → 只用 Dense 结果）
  - 但如果 BM25 索引不存在（N=0），返回空列表而非异常（无索引时不阻塞检索）

接口签名：
  SparseRetriever(settings: Settings, bm25_indexer: BM25Indexer | None = None, vector_store: BaseVectorStore | None = None)
  retrieve(keywords: list[str], top_k: int = 10, trace: TraceContext | None = None) -> list[RetrievalResult]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from ingestion.storage.bm25_indexer import BM25Indexer
    from libs.vector_store.base_vector_store import BaseVectorStore

logger = logging.getLogger(__name__)


class SparseRetriever:
    """稀疏检索器 — BM25 关键词检索 + VectorStore 获取原文

    知识点：SparseRetriever 的设计原则
      - 单一职责：只做 Sparse 检索（keywords → BM25 → VectorStore.get_by_ids → RetrievalResult）
      - 依赖注入：bm25_indexer 和 vector_store 可注入，便于测试
      - Fail-Fast：失败直接抛异常，由上层 HybridSearch 负责降级
      - 空索引保护：BM25 索引不存在时返回空列表（不阻塞检索）
      - 面试考点："为什么 Sparse 需要 VectorStore 参与？" → BM25 只存 (chunk_id, score)，
        获取原文需要回查 VectorStore

    接口签名：
      SparseRetriever(settings, bm25_indexer=None, vector_store=None)
      retrieve(keywords, top_k=10, trace=None) -> list[RetrievalResult]
    """

    def __init__(
        self,
        settings: Settings,
        bm25_indexer: BM25Indexer | None = None,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        """初始化 SparseRetriever

        接口签名：SparseRetriever(settings, bm25_indexer=None, vector_store=None)
        入参：
          - settings: 全局配置
          - bm25_indexer: 可选，注入 BM25Indexer 实例（测试用 Mock）
          - vector_store: 可选，注入 BaseVectorStore 实例（测试用 Mock）

        知识点：依赖注入模式（与 DenseRetriever 一致）
          - 不注入时从 settings 通过工厂或直接创建（生产环境）
          - 注入时直接使用（测试隔离）
        """
        self._settings = settings

        # BM25Indexer：注入 or 创建
        if bm25_indexer is not None:
            self._bm25_indexer = bm25_indexer
        else:
            self._bm25_indexer = BM25Indexer(
                persist_path="data/db/bm25",
                k1=1.2,
                b=0.75,
            )
            # 尝试加载已有索引
            try:
                self._bm25_indexer.load()
            except FileNotFoundError:
                logger.warning("BM25 索引文件不存在，SparseRetriever 将返回空结果")

        # VectorStore：注入 or 工厂创建
        if vector_store is not None:
            self._vector_store = vector_store
        else:
            from libs.vector_store.vector_store_factory import VectorStoreFactory
            self._vector_store = VectorStoreFactory.create(settings.vector_store)

    # --------------------------------------------------------
    # 主入口：retrieve
    # --------------------------------------------------------

    def retrieve(
        self,
        keywords: list[str],
        top_k: int = 10,
        trace: TraceContext | None = None,
    ) -> list[Any]:
        """BM25 关键词检索

        接口签名：retrieve(keywords, top_k=10, trace=None) -> list[RetrievalResult]
        入参：
          - keywords: 关键词列表（来自 QueryProcessor.process().keywords）
          - top_k: 返回前 K 个结果
          - trace: 可选的追踪上下文
        出参：RetrievalResult 列表，按 BM25 score 降序排列
        异常：
          - VectorStoreError: VectorStore.get_by_ids 调用失败
          - （BM25 查询本身不失败，纯本地计算）

        内部流程：
          1. 校验 keywords 非空
          2. keywords → bm25_indexer.query(keywords, top_k) → [{chunk_id, score}]
          3. 提取 chunk_ids
          4. chunk_ids → vector_store.get_by_ids(chunk_ids) → [{id, text, metadata}]
          5. 合并 score 与 text/metadata，组装为 RetrievalResult
          6. 记录 trace
          7. 返回 list[RetrievalResult]

        面试考点：
          "SparseRetriever.retrieve 做了什么？" → keywords → BM25 query → get_by_ids → RetrievalResult
          "为什么要 get_by_ids？" → BM25 索引只存 (chunk_id, score)，原文在 VectorStore
        """
        import time

        from core.types import RetrievalResult

        start = time.perf_counter()

        # 1. 校验 keywords
        if not keywords:
            if trace is not None:
                trace.record_stage(
                    "sparse_retriever",
                    {"keywords_count": 0, "result_count": 0, "reason": "empty_keywords"},
                    duration_ms=0.0,
                )
            return []

        # 空索引保护：BM25 未构建时返回空列表
        if not self._bm25_indexer.is_built:
            logger.debug("BM25 索引未构建，SparseRetriever 返回空结果")
            if trace is not None:
                trace.record_stage(
                    "sparse_retriever",
                    {"keywords_count": len(keywords), "result_count": 0, "reason": "index_not_built"},
                    duration_ms=0.0,
                )
            return []

        # 2. BM25 关键词检索
        bm25_start = time.perf_counter()
        bm25_results = self._bm25_indexer.query(keywords, top_k)
        bm25_duration_ms = (time.perf_counter() - bm25_start) * 1000

        if not bm25_results:
            if trace is not None:
                trace.record_stage(
                    "sparse_retriever",
                    {"keywords_count": len(keywords), "result_count": 0, "reason": "no_match"},
                    duration_ms=round(bm25_duration_ms, 2),
                )
            return []

        # 3. 提取 chunk_ids（跳过缺少 chunk_id 的异常条目）
        chunk_ids = [r["chunk_id"] for r in bm25_results if "chunk_id" in r]

        # 4. 构建 chunk_id → score 映射
        score_map: dict[str, float] = {
            r["chunk_id"]: r["score"] for r in bm25_results if "chunk_id" in r
        }

        # 5. VectorStore 获取原文
        ids_start = time.perf_counter()
        records = self._vector_store.get_by_ids(chunk_ids)
        ids_duration_ms = (time.perf_counter() - ids_start) * 1000

        # 6. 组装 RetrievalResult
        results: list[RetrievalResult] = []
        for record in records:
            chunk_id = record.get("id", "")
            if not chunk_id:
                continue
            results.append(RetrievalResult(
                chunk_id=chunk_id,
                score=score_map.get(chunk_id, 0.0),
                text=record.get("text", ""),
                metadata=dict(record.get("metadata", {})),
            ))

        # 按 score 降序排序（BM25 查询已排序，但 get_by_ids 可能打乱顺序）
        results.sort(key=lambda r: (-r.score, r.chunk_id))

        # 7. 记录 trace
        if trace is not None:
            total_duration_ms = (time.perf_counter() - start) * 1000
            trace.record_stage(
                "sparse_retriever",
                {
                    "keywords_count": len(keywords),
                    "keywords": keywords[:20],
                    "bm25_result_count": len(bm25_results),
                    "result_count": len(results),
                    "bm25_duration_ms": round(bm25_duration_ms, 2),
                    "get_by_ids_duration_ms": round(ids_duration_ms, 2),
                },
                duration_ms=round(total_duration_ms, 2),
            )

        logger.debug(
            "SparseRetriever: keywords=%d → bm25=%d → results=%d (bm25=%.1fms, ids=%.1fms)",
            len(keywords),
            len(bm25_results),
            len(results),
            bm25_duration_ms,
            ids_duration_ms,
        )

        return results

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def bm25_indexer(self) -> BM25Indexer:
        """返回 BM25Indexer 实例"""
        return self._bm25_indexer

    @property
    def vector_store(self) -> BaseVectorStore:
        """返回 VectorStore 实例"""
        return self._vector_store

