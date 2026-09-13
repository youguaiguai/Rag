"""
DenseRetriever — 稠密向量检索（Query Embedding + VectorStore 检索）

知识点：DenseRetriever 在 RAG 检索链路中的位置
  - 检索链路：Query → QueryProcessor → DenseRetriever + SparseRetriever → Fusion → Reranker
  - 职责：将查询文本 → embedding 向量 → 调用 VectorStore 语义检索 → 返回 RetrievalResult 列表
  - 与 SparseRetriever 互补：Dense 捕获语义相似性，Sparse 捕获精确匹配

DenseRetriever 的核心流程（面试考点）：
  1. query → embedding_client.embed([query]) → query_vector
  2. query_vector → vector_store.query(vector, top_k, filters) → list[QueryResult]
  3. QueryResult → RetrievalResult（id → chunk_id 字段映射）
  - 面试考点："DenseRetriever 和 SparseRetriever 的区别？" → Dense 用向量语义检索，Sparse 用 BM25 关键词检索

依赖注入设计（面试考点）：
  - __init__(settings, embedding_client?, vector_store?)
  - embedding_client 和 vector_store 可选注入，用于测试隔离
  - 不注入时从 settings 自动创建（生产环境使用）
  - 好处：测试时用 Mock 替代真实 API，不依赖外部服务

降级策略：
  - DenseRetriever 是检索链路核心组件，Fail-Fast：Embedding/VectorStore 失败直接抛异常
  - HybridSearch 层负责降级（Dense 失败 → 只用 Sparse 结果）

接口签名：
  DenseRetriever(settings: Settings, embedding_client: BaseEmbedding | None = None, vector_store: BaseVectorStore | None = None)
  retrieve(query: str, top_k: int = 10, filters: dict | None = None, trace: TraceContext | None = None) -> list[RetrievalResult]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from libs.embedding.base_embedding import BaseEmbedding
    from libs.vector_store.base_vector_store import BaseVectorStore

logger = logging.getLogger(__name__)


class DenseRetriever:
    """稠密向量检索器 — Query Embedding + VectorStore 语义检索

    知识点：DenseRetriever 的设计原则
      - 单一职责：只做 Dense 检索（query → embedding → vector_store.query）
      - 依赖注入：embedding_client 和 vector_store 可注入，便于测试
      - Fail-Fast：Embedding/VectorStore 失败直接抛异常，由上层 HybridSearch 负责降级
      - 面试考点："为什么 DenseRetriever 不自己降级？" → HybridSearch 有备用路径（Sparse），单路失败不阻塞

    接口签名：
      DenseRetriever(settings, embedding_client=None, vector_store=None)
      retrieve(query, top_k=10, filters=None, trace=None) -> list[RetrievalResult]
    """

    def __init__(
        self,
        settings: Settings,
        embedding_client: BaseEmbedding | None = None,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        """初始化 DenseRetriever

        接口签名：DenseRetriever(settings, embedding_client=None, vector_store=None)
        入参：
          - settings: 全局配置
          - embedding_client: 可选，注入 BaseEmbedding 实例（测试用 Mock）
          - vector_store: 可选，注入 BaseVectorStore 实例（测试用 Mock）
        出参：None

        知识点：依赖注入模式
          - 不注入时从 settings 通过工厂创建（生产环境）
          - 注入时直接使用（测试隔离）
          - 好处：上层不依赖具体实现，只依赖接口
          - 面试考点："为什么要依赖注入？" → 测试隔离 + 灵活替换实现
        """
        self._settings = settings

        # Embedding 客户端：注入 or 工厂创建
        if embedding_client is not None:
            self._embedding_client = embedding_client
        else:
            from libs.embedding.embedding_factory import EmbeddingFactory
            self._embedding_client = EmbeddingFactory.create(settings.embedding)

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
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        trace: TraceContext | None = None,
    ) -> list[Any]:
        """稠密向量检索

        接口签名：retrieve(query, top_k=10, filters=None, trace=None) -> list[RetrievalResult]
        入参：
          - query: 查询字符串（非空）
          - top_k: 返回最相似的 K 条结果
          - filters: 可选的 metadata 过滤条件
          - trace: 可选的追踪上下文
        出参：RetrievalResult 列表，按 score 降序排列
        异常：
          - ValueError: 查询为空
          - EmbeddingError: Embedding API 调用失败
          - VectorStoreError: 向量数据库查询失败

        内部流程：
          1. 校验 query 非空
          2. query → embedding_client.embed([query]) → query_vector
          3. query_vector → vector_store.query(vector, top_k, filters) → list[QueryResult]
          4. QueryResult → RetrievalResult（id → chunk_id 字段映射）
          5. 记录 trace
          6. 返回 list[RetrievalResult]

        面试考点：
          "DenseRetriever.retrieve 做了什么？" → query → embed → vector_store.query → RetrievalResult
          "QueryResult 和 RetrievalResult 的区别？" → QueryResult 是 libs 层输出，
            RetrievalResult 是 core 层统一格式，id → chunk_id
        """
        import time

        from core.types import RetrievalResult

        start = time.perf_counter()

        # 1. 校验查询
        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "查询不能为空，必须是非空字符串"
                f"（收到 type={type(query).__name__}）"
            )

        raw_query = query.strip()

        # 2. Query → Embedding
        # embed() 接受 list[str]，返回 list[list[float]]
        # 查询只有一条文本，所以取 results[0]
        embed_start = time.perf_counter()
        vectors = self._embedding_client.embed([raw_query])
        embed_duration_ms = (time.perf_counter() - embed_start) * 1000

        if not vectors or len(vectors) == 0:
            raise RuntimeError("Embedding 返回空向量列表，无法执行检索")

        query_vector = vectors[0]

        # 3. VectorStore 检索
        query_start = time.perf_counter()
        query_results = self._vector_store.query(
            vector=query_vector,
            top_k=top_k,
            filters=filters,
        )
        query_duration_ms = (time.perf_counter() - query_start) * 1000

        # 4. QueryResult → RetrievalResult 转换
        # 字段映射：id → chunk_id，其余直接复制
        results: list[RetrievalResult] = [
            RetrievalResult(
                chunk_id=qr.id,
                score=qr.score,
                text=qr.text,
                metadata=dict(qr.metadata),
            )
            for qr in query_results
        ]

        # 5. 记录 trace
        if trace is not None:
            total_duration_ms = (time.perf_counter() - start) * 1000
            trace.record_stage(
                "dense_retriever",
                {
                    "query": raw_query[:200],  # 截断防止过长
                    "top_k": top_k,
                    "result_count": len(results),
                    "embed_duration_ms": round(embed_duration_ms, 2),
                    "query_duration_ms": round(query_duration_ms, 2),
                    "embedding_model": self._embedding_client.model_name,
                },
                duration_ms=round(total_duration_ms, 2),
            )

        logger.debug(
            "DenseRetriever: query=%r → %d results (embed=%.1fms, query=%.1fms)",
            raw_query[:100],
            len(results),
            embed_duration_ms,
            query_duration_ms,
        )

        return results

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def embedding_client(self) -> BaseEmbedding:
        """返回 Embedding 客户端实例（用于上层调试和测试验证）"""
        return self._embedding_client

    @property
    def vector_store(self) -> BaseVectorStore:
        """返回 VectorStore 实例（用于上层调试和测试验证）"""
        return self._vector_store

