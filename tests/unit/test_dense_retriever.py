"""
DenseRetriever 单元测试 — D2: Query Embedding + VectorStore 检索

测试策略：
  - 使用 MockEmbedding + MockVectorStore 隔离，不依赖真实 API/数据库
  - 验收标准全覆盖：
    1. RetrievalResult 类型已定义并可序列化
    2. 对输入 query 能生成 embedding 并调用 VectorStore 检索
    3. 返回结果包含 chunk_id、score、text、metadata
    4. mock EmbeddingClient 和 VectorStore 时能正确编排调用
    5. QueryResult → RetrievalResult 的字段映射正确（id → chunk_id）
    6. filters 透传到 VectorStore
    7. top_k 透传到 VectorStore
    8. 异常处理：空查询、Embedding 失败、VectorStore 失败

测试分类（25 个）：
  - RetrievalResult 数据契约（5）
  - 基础检索流程（4）
  - QueryResult → RetrievalResult 字段映射（3）
  - filters 透传（3）
  - top_k 透传（2）
  - 依赖注入（2）
  - 异常处理（3）
  - Trace 集成（2）
  - 只读属性（1）
"""

from __future__ import annotations

import pytest
from core.query_engine.dense_retriever import DenseRetriever
from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import RetrievalResult
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from libs.vector_store.base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)
from typing import Any


# ============================================================
# MockEmbedding — 可编程 Embedding 测试桩
# ============================================================

class MockEmbedding(BaseEmbedding):
    """可编程 Mock Embedding — 记录调用 + 可配置返回值/异常

    知识点：Mock vs Stub
      - Stub（桩）：返回固定值
      - Mock（模拟对象）：记录调用 + 可配置行为 + 可验证调用次数
    """

    def __init__(
        self,
        dimensions: int = 128,
        error: Exception | None = None,
        empty_result: bool = False,
    ) -> None:
        self._model = "mock-embedding-model"
        self._dims = dimensions
        self._error = error
        self._empty_result = empty_result
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.calls.append(texts)
        if self._error is not None:
            raise self._error
        if self._empty_result:
            return []
        # 返回与输入数量一致的向量
        return [[0.01 * (i + 1) for i in range(self._dims)] for _ in texts]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dims


# ============================================================
# MockVectorStore — 可编程 VectorStore 测试桩
# ============================================================

class MockVectorStore(BaseVectorStore):
    """可编程 Mock VectorStore — 记录调用 + 可配置返回值/异常"""

    def __init__(
        self,
        results: list[QueryResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._results = results or []
        self._error = error
        self.query_calls: list[dict[str, Any]] = []

    def upsert(self, records: list[VectorRecord]) -> None:
        pass

    def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[QueryResult]:
        self.query_calls.append({
            "vector": vector,
            "top_k": top_k,
            "filters": filters,
        })
        if self._error is not None:
            raise self._error
        return list(self._results)

    def delete(self, ids: list[str]) -> int:
        return 0

    def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        return []

    def delete_by_metadata(self, filter: dict[str, Any]) -> int:
        return 0


# ============================================================
# 辅助函数
# ============================================================

def _make_settings() -> Settings:
    """创建测试用 Settings"""
    s = Settings()
    s.embedding.provider = "fake"
    s.embedding.dimensions = 128
    s.vector_store.backend = "fake"
    return s


def _make_query_results(count: int = 3) -> list[QueryResult]:
    """创建测试用 QueryResult 列表"""
    return [
        QueryResult(
            id=f"chunk_{i:04d}_abcd1234",
            score=0.9 - i * 0.1,
            text=f"This is chunk {i} text content.",
            metadata={"doc_id": f"doc_{i}", "source_ref": f"doc.md#chunk={i}"},
        )
        for i in range(count)
    ]


# ============================================================
# TestRetrievalResultContract — RetrievalResult 数据契约验证
# ============================================================

class TestRetrievalResultContract:
    """RetrievalResult 数据契约验证（5 个测试）

    知识点：RetrievalResult 是检索链路的统一输出格式
      - chunk_id: Chunk ID（从 QueryResult.id 映射而来）
      - score: 相似度分数
      - text: 匹配文本
      - metadata: 元数据
    """

    def test_retrieval_result_has_chunk_id_field(self) -> None:
        """RetrievalResult 必须包含 chunk_id 字段"""
        result = RetrievalResult(chunk_id="chunk_001", score=0.9, text="hello")
        assert hasattr(result, "chunk_id")
        assert result.chunk_id == "chunk_001"

    def test_retrieval_result_has_score_field(self) -> None:
        """RetrievalResult 必须包含 score 字段"""
        result = RetrievalResult(chunk_id="chunk_001", score=0.95, text="hello")
        assert result.score == 0.95

    def test_retrieval_result_has_text_field(self) -> None:
        """RetrievalResult 必须包含 text 字段"""
        result = RetrievalResult(chunk_id="chunk_001", score=0.9, text="hello world")
        assert result.text == "hello world"

    def test_retrieval_result_has_metadata_field(self) -> None:
        """RetrievalResult 必须包含 metadata 字段，默认空 dict"""
        result = RetrievalResult(chunk_id="chunk_001", score=0.9, text="hello")
        assert isinstance(result.metadata, dict)
        assert result.metadata == {}

    def test_retrieval_result_all_fields(self) -> None:
        """RetrievalResult 所有字段可正确赋值"""
        metadata = {"doc_type": "pdf", "title": "Test Doc"}
        result = RetrievalResult(
            chunk_id="chunk_0001_abcd1234",
            score=0.85,
            text="This is the text content.",
            metadata=metadata,
        )
        assert result.chunk_id == "chunk_0001_abcd1234"
        assert result.score == 0.85
        assert result.text == "This is the text content."
        assert result.metadata == metadata


# ============================================================
# TestBasicRetrievalFlow — 基础检索流程
# ============================================================

class TestBasicRetrievalFlow:
    """基础检索流程测试（4 个测试）

    知识点：DenseRetriever 的核心流程
      query -> embed([query]) -> vector -> vector_store.query() -> QueryResult -> RetrievalResult
    """

    def test_basic_retrieve_returns_results(self) -> None:
        """基础检索返回 RetrievalResult 列表"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(3))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        results = retriever.retrieve("what is machine learning?", top_k=5)

        assert len(results) == 3
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_retrieve_calls_embed_with_query(self) -> None:
        """检索时调用 embed 并传入查询文本"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(2))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        retriever.retrieve("what is RAG?", top_k=5)

        # embed 应被调用一次，传入 [query]
        assert len(mock_embed.calls) == 1
        assert mock_embed.calls[0] == ["what is RAG?"]

    def test_retrieve_calls_vector_store_query(self) -> None:
        """检索时调用 vector_store.query"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(2))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        retriever.retrieve("test query", top_k=10)

        # query 应被调用一次
        assert len(mock_store.query_calls) == 1
        call = mock_store.query_calls[0]
        assert call["top_k"] == 10

    def test_results_ordered_by_score_desc(self) -> None:
        """检索结果按 score 降序排列（由 VectorStore 保证）"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(3))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        results = retriever.retrieve("test", top_k=5)

        # _make_query_results 返回 0.9, 0.8, 0.7
        assert results[0].score >= results[1].score >= results[2].score


# ============================================================
# TestFieldMapping — QueryResult -> RetrievalResult 字段映射
# ============================================================

class TestFieldMapping:
    """QueryResult -> RetrievalResult 字段映射测试（3 个测试）

    知识点：字段映射
      - QueryResult.id -> RetrievalResult.chunk_id（字段重命名）
      - QueryResult.score -> RetrievalResult.score（直接复制）
      - QueryResult.text -> RetrievalResult.text（直接复制）
      - QueryResult.metadata -> RetrievalResult.metadata（浅拷贝）
    """

    def test_id_to_chunk_id_mapping(self) -> None:
        """QueryResult.id 正确映射为 RetrievalResult.chunk_id"""
        qr = [QueryResult(id="chunk_0001_abcd1234", score=0.9, text="text", metadata={})]
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=qr)
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        results = retriever.retrieve("test", top_k=1)

        assert len(results) == 1
        assert results[0].chunk_id == "chunk_0001_abcd1234"

    def test_score_and_text_preserved(self) -> None:
        """QueryResult.score 和 text 正确保留"""
        qr = [QueryResult(id="c1", score=0.85, text="hello world", metadata={"k": "v"})]
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=qr)
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        results = retriever.retrieve("test", top_k=1)

        assert results[0].score == 0.85
        assert results[0].text == "hello world"

    def test_metadata_copied_not_shared(self) -> None:
        """metadata 是浅拷贝，不共享引用"""
        original_metadata = {"doc_id": "doc1", "source_ref": "doc.md#chunk=0"}
        qr = [QueryResult(id="c1", score=0.9, text="text", metadata=original_metadata)]
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=qr)
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        results = retriever.retrieve("test", top_k=1)

        # metadata 值一致
        assert results[0].metadata == original_metadata
        # 但不是同一个对象
        assert results[0].metadata is not original_metadata


# ============================================================
# TestFiltersPassthrough — filters 透传
# ============================================================

class TestFiltersPassthrough:
    """filters 透传测试（3 个测试）

    知识点：filters 设计
      - DenseRetriever 不处理 filters，原样透传给 VectorStore
      - VectorStore 负责实际过滤（如 Chroma 的 where 条件）
    """

    def test_none_filters_passed_to_vector_store(self) -> None:
        """None filters 正确透传到 VectorStore"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(1))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        retriever.retrieve("test", top_k=5, filters=None)

        assert mock_store.query_calls[0]["filters"] is None

    def test_dict_filters_passed_to_vector_store(self) -> None:
        """dict filters 正确透传到 VectorStore"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(1))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        filters = {"doc_type": "pdf", "collection": "default"}
        retriever.retrieve("test", top_k=5, filters=filters)

        assert mock_store.query_calls[0]["filters"] == filters

    def test_empty_dict_filters_passed_through(self) -> None:
        """空 dict filters 正确透传"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(1))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        retriever.retrieve("test", top_k=5, filters={})

        assert mock_store.query_calls[0]["filters"] == {}


# ============================================================
# TestTopKPassthrough — top_k 透传
# ============================================================

class TestTopKPassthrough:
    """top_k 透传测试（2 个测试）"""

    def test_default_top_k(self) -> None:
        """默认 top_k=10 透传到 VectorStore"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(1))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        retriever.retrieve("test")

        assert mock_store.query_calls[0]["top_k"] == 10

    def test_custom_top_k(self) -> None:
        """自定义 top_k 透传到 VectorStore"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(1))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        retriever.retrieve("test", top_k=20)

        assert mock_store.query_calls[0]["top_k"] == 20


# ============================================================
# TestDependencyInjection — 依赖注入
# ============================================================

class TestDependencyInjection:
    """依赖注入测试（2 个测试）

    知识点：依赖注入模式
      - embedding_client 和 vector_store 可注入
      - 不注入时从 settings 通过工厂创建
    """

    def test_injected_clients_are_used(self) -> None:
        """注入的 embedding_client 和 vector_store 被使用"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(2))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        retriever.retrieve("test", top_k=5)

        # 验证注入的实例被调用
        assert len(mock_embed.calls) == 1
        assert len(mock_store.query_calls) == 1

    def test_properties_return_injected_instances(self) -> None:
        """只读属性返回注入的实例"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=[])
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        assert retriever.embedding_client is mock_embed
        assert retriever.vector_store is mock_store


# ============================================================
# TestExceptionHandling — 异常处理
# ============================================================

class TestExceptionHandling:
    """异常处理测试（3 个测试）

    知识点：DenseRetriever 是 Fail-Fast
      - 空查询 -> ValueError
      - Embedding 失败 -> EmbeddingError 透传
      - VectorStore 失败 -> VectorStoreError 透传
    """

    def test_empty_query_raises_value_error(self) -> None:
        """空查询抛 ValueError"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=[])
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        with pytest.raises(ValueError, match="查询不能为空"):
            retriever.retrieve("")

    def test_embedding_error_propagates(self) -> None:
        """Embedding 失败时异常透传（Fail-Fast）"""
        mock_embed = MockEmbedding(error=EmbeddingError("API timeout"))
        mock_store = MockVectorStore(results=[])
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        with pytest.raises(EmbeddingError, match="API timeout"):
            retriever.retrieve("test query")

    def test_vector_store_error_propagates(self) -> None:
        """VectorStore 失败时异常透传（Fail-Fast）"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(error=VectorStoreError("DB connection failed"))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        with pytest.raises(VectorStoreError, match="DB connection failed"):
            retriever.retrieve("test query")


# ============================================================
# TestTraceIntegration — Trace 集成
# ============================================================

class TestTraceIntegration:
    """Trace 集成测试（2 个测试）

    知识点：TraceContext 使用
      - retrieve() 可选接受 trace 参数
      - trace 不为 None 时记录 dense_retriever 阶段
      - 记录内容：query, top_k, result_count, embed/query duration
    """

    def test_trace_recorded_when_provided(self) -> None:
        """提供 trace 时记录 dense_retriever 阶段"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(3))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        trace = TraceContext()
        retriever.retrieve("machine learning", top_k=5, trace=trace)

        stages = trace.get_stages("dense_retriever")
        assert len(stages) == 1
        stage = stages[0]
        assert stage.data["query"] == "machine learning"
        assert stage.data["top_k"] == 5
        assert stage.data["result_count"] == 3
        assert stage.data["embed_duration_ms"] is not None
        assert stage.data["query_duration_ms"] is not None
        assert stage.data["embedding_model"] == "mock-embedding-model"
        assert stage.duration_ms is not None
        assert stage.duration_ms >= 0

    def test_no_trace_no_error(self) -> None:
        """不提供 trace 时不报错"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=_make_query_results(1))
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        # trace=None 应正常工作
        results = retriever.retrieve("test", trace=None)
        assert len(results) == 1


# ============================================================
# TestReadOnlyProperties — 只读属性
# ============================================================

class TestReadOnlyProperties:
    """只读属性测试（1 个测试）"""

    def test_properties_accessible(self) -> None:
        """embedding_client 和 vector_store 属性可访问"""
        mock_embed = MockEmbedding()
        mock_store = MockVectorStore(results=[])
        retriever = DenseRetriever(_make_settings(), mock_embed, mock_store)

        # 属性应返回注入的实例
        assert retriever.embedding_client is mock_embed
        assert retriever.vector_store is mock_store
        assert retriever.embedding_client.model_name == "mock-embedding-model"
        assert retriever.embedding_client.dimensions == 128

