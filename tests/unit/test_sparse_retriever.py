"""
SparseRetriever 单元测试 — D3: BM25 关键词检索 + VectorStore 获取原文

测试策略：
  - 使用 MockBM25Indexer + MockVectorStore 隔离，不依赖真实索引/数据库
  - 验收标准全覆盖：
    1. BaseVectorStore.get_by_ids() 已实现
    2. 关键词检索能正确编排 BM25 + VectorStore 调用
    3. 返回结果包含完整的 text 和 metadata
    4. QueryResult → RetrievalResult 字段映射正确
    5. 空 keywords 保护
    6. 空索引保护（BM25 未构建时返回空列表）
    7. 异常处理

测试分类（24 个）：
  - 基础检索流程（4）
  - 字段映射与结果组装（4）
  - 空输入保护（3）
  - 空索引保护（2）
  - 依赖注入（2）
  - 异常处理（2）
  - Trace 集成（2）
  - 结果排序（2）
  - 只读属性（1）
  - 边界情况（2）
"""

from __future__ import annotations

import pytest
from core.query_engine.sparse_retriever import SparseRetriever
from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import RetrievalResult
from ingestion.storage.bm25_indexer import BM25Indexer
from libs.vector_store.base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)
from typing import Any


# ============================================================
# MockBM25Indexer — 可编程 BM25Indexer 测试桩
# ============================================================

class MockBM25Indexer(BM25Indexer):
    """可编程 Mock BM25Indexer — 记录调用 + 可配置返回值/异常

    继承 BM25Indexer 但以内存模式运行（不读写文件）
    """

    def __init__(
        self,
        results: list[dict[str, Any]] | None = None,
        is_built: bool = True,
    ) -> None:
        # 不调用 super().__init__() 避免文件路径依赖
        # 直接设置必要的内部状态
        self._persist_dir = None  # type: ignore
        self._index_path = None  # type: ignore
        self._k1 = 1.2
        self._b = 0.75
        self._index = {
            "N": 10 if is_built else 0,
            "avgdl": 5.0,
            "k1": 1.2,
            "b": 0.75,
            "index": {} if not is_built else {"test": {"idf": 1.0, "postings": []}},
        }
        self._doc_lengths = {}
        self._mock_results = results or []
        self.query_calls: list[dict[str, Any]] = []

    def query(
        self,
        keywords: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        self.query_calls.append({"keywords": keywords, "top_k": top_k})
        return list(self._mock_results)

    # 兼容 search 方法（继承 BM25Indexer 的 search 但可能不被测试直接调用）
    def search(
        self,
        query_terms: dict[str, float],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        return [
            (r["chunk_id"], r["score"])
            for r in self._mock_results
        ]


# ============================================================
# MockVectorStore — 可编程 VectorStore 测试桩
# ============================================================

class MockVectorStore(BaseVectorStore):
    """可编程 Mock VectorStore — 记录调用 + 可配置返回值/异常"""

    def __init__(
        self,
        records: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._records = records or []
        self._error = error
        self.get_by_ids_calls: list[list[str]] = []

    def upsert(self, records: list[VectorRecord]) -> None:
        pass

    def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[QueryResult]:
        return []

    def delete(self, ids: list[str]) -> int:
        return 0

    def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        self.get_by_ids_calls.append(ids)
        if self._error is not None:
            raise self._error
        return list(self._records)

    def delete_by_metadata(self, filter: dict[str, Any]) -> int:
        return 0


# ============================================================
# 辅助函数
# ============================================================

def _make_settings() -> Settings:
    """创建测试用 Settings"""
    s = Settings()
    s.vector_store.backend = "fake"
    return s


def _make_bm25_results() -> list[dict[str, Any]]:
    """创建测试用 BM25 查询结果"""
    return [
        {"chunk_id": "chunk_0001_abcd1234", "score": 2.5},
        {"chunk_id": "chunk_0002_efgh5678", "score": 1.8},
        {"chunk_id": "chunk_0003_ijkl9012", "score": 1.2},
    ]


def _make_vector_store_records() -> list[dict[str, Any]]:
    """创建测试用 VectorStore 记录"""
    return [
        {
            "id": "chunk_0001_abcd1234",
            "text": "This is the first chunk about machine learning.",
            "metadata": {"doc_id": "doc_1", "title": "ML Basics"},
        },
        {
            "id": "chunk_0002_efgh5678",
            "text": "This is the second chunk about deep learning.",
            "metadata": {"doc_id": "doc_2", "title": "DL Advanced"},
        },
        {
            "id": "chunk_0003_ijkl9012",
            "text": "This is the third chunk about neural networks.",
            "metadata": {"doc_id": "doc_3", "title": "NN Intro"},
        },
    ]


# ============================================================
# TestBasicRetrievalFlow — 基础检索流程
# ============================================================

class TestBasicRetrievalFlow:
    """基础检索流程测试（4 个测试）

    知识点：SparseRetriever 的核心流程
      keywords → BM25 query → get_by_ids → RetrievalResult
    """

    def test_basic_retrieve_returns_results(self) -> None:
        """基础检索返回 RetrievalResult 列表"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["machine", "learning"], top_k=5)

        assert len(results) == 3
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_retrieve_calls_bm25_query(self) -> None:
        """检索时调用 bm25_indexer.query"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        retriever.retrieve(["python", "rag"], top_k=10)

        assert len(bm25.query_calls) == 1
        assert bm25.query_calls[0]["keywords"] == ["python", "rag"]
        assert bm25.query_calls[0]["top_k"] == 10

    def test_retrieve_calls_vector_store_get_by_ids(self) -> None:
        """检索时调用 vector_store.get_by_ids 获取原文"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        retriever.retrieve(["test"], top_k=5)

        assert len(store.get_by_ids_calls) == 1
        # 应传入 BM25 返回的 chunk_ids
        assert store.get_by_ids_calls[0] == [
            "chunk_0001_abcd1234",
            "chunk_0002_efgh5678",
            "chunk_0003_ijkl9012",
        ]

    def test_retrieve_preserves_bm25_score(self) -> None:
        """检索结果保留 BM25 分数"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)

        # 验证分数
        score_map = {r.chunk_id: r.score for r in results}
        assert score_map["chunk_0001_abcd1234"] == 2.5
        assert score_map["chunk_0002_efgh5678"] == 1.8
        assert score_map["chunk_0003_ijkl9012"] == 1.2


# ============================================================
# TestFieldMapping — 字段映射与结果组装
# ============================================================

class TestFieldMapping:
    """字段映射与结果组装测试（4 个测试）

    知识点：字段映射
      - BM25 chunk_id → RetrievalResult.chunk_id
      - BM25 score → RetrievalResult.score
      - VectorStore text → RetrievalResult.text
      - VectorStore metadata → RetrievalResult.metadata
    """

    def test_all_fields_assembled(self) -> None:
        """所有字段正确组装"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)

        r1 = results[0]
        assert r1.chunk_id == "chunk_0001_abcd1234"
        assert r1.score == 2.5
        assert r1.text == "This is the first chunk about machine learning."
        assert r1.metadata["title"] == "ML Basics"

    def test_text_correctly_mapped(self) -> None:
        """text 字段正确映射"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)
        texts = {r.chunk_id: r.text for r in results}

        assert "machine learning" in texts["chunk_0001_abcd1234"]
        assert "deep learning" in texts["chunk_0002_efgh5678"]
        assert "neural networks" in texts["chunk_0003_ijkl9012"]

    def test_metadata_copied_not_shared(self) -> None:
        """metadata 是拷贝，不共享引用"""
        bm25 = MockBM25Indexer(results=[
            {"chunk_id": "chunk_0001_abcd1234", "score": 1.0},
        ])
        store = MockVectorStore(records=[
            {"id": "chunk_0001_abcd1234", "text": "text", "metadata": {"key": "value"}},
        ])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=1)

        # 修改原始记录不应影响结果
        store._records[0]["metadata"]["key"] = "modified"
        assert results[0].metadata["key"] == "value"

    def test_result_count_matches_available_records(self) -> None:
        """返回结果数量 = min(BM25 结果数, VectorStore 返回数)"""
        # BM25 返回 3 条，但 VectorStore 只有 2 条
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records()[:2])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)

        assert len(results) == 2


# ============================================================
# TestEmptyInputProtection — 空输入保护
# ============================================================

class TestEmptyInputProtection:
    """空输入保护测试（3 个测试）"""

    def test_empty_keywords_returns_empty_list(self) -> None:
        """空 keywords 返回空列表"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve([], top_k=5)

        assert results == []
        # BM25 不应被调用
        assert len(bm25.query_calls) == 0

    def test_none_like_empty_returns_empty(self) -> None:
        """空列表不触发 VectorStore 调用"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        retriever.retrieve([], top_k=10)

        # VectorStore.get_by_ids 不应被调用
        assert len(store.get_by_ids_calls) == 0

    def test_empty_keywords_traces_reason(self) -> None:
        """空 keywords 时 trace 记录原因"""
        bm25 = MockBM25Indexer(results=[])
        store = MockVectorStore(records=[])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        trace = TraceContext()
        retriever.retrieve([], trace=trace)

        stages = trace.get_stages("sparse_retriever")
        assert len(stages) == 1
        assert stages[0].data["reason"] == "empty_keywords"


# ============================================================
# TestEmptyIndexProtection — 空索引保护
# ============================================================

class TestEmptyIndexProtection:
    """空索引保护测试（2 个测试）

    知识点：BM25 索引未构建时返回空列表而非异常
      - 避免阻塞检索流程
      - HybridSearch 可降级到 Dense-only 模式
    """

    def test_unbuilt_index_returns_empty_list(self) -> None:
        """BM25 索引未构建时返回空列表"""
        bm25 = MockBM25Indexer(is_built=False)
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)

        assert results == []
        # BM25 不应被调用
        assert len(bm25.query_calls) == 0

    def test_unbuilt_index_does_not_call_vector_store(self) -> None:
        """BM25 索引未构建时不调用 VectorStore"""
        bm25 = MockBM25Indexer(is_built=False)
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        retriever.retrieve(["test"], top_k=5)

        assert len(store.get_by_ids_calls) == 0


# ============================================================
# TestDependencyInjection — 依赖注入
# ============================================================

class TestDependencyInjection:
    """依赖注入测试（2 个测试）"""

    def test_injected_instances_are_used(self) -> None:
        """注入的 bm25_indexer 和 vector_store 被使用"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        retriever.retrieve(["test"], top_k=5)

        assert len(bm25.query_calls) == 1
        assert len(store.get_by_ids_calls) == 1

    def test_properties_return_injected_instances(self) -> None:
        """只读属性返回注入的实例"""
        bm25 = MockBM25Indexer(results=[])
        store = MockVectorStore(records=[])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        assert retriever.bm25_indexer is bm25
        assert retriever.vector_store is store


# ============================================================
# TestExceptionHandling — 异常处理
# ============================================================

class TestExceptionHandling:
    """异常处理测试（2 个测试）

    知识点：SparseRetriever 是 Fail-Fast
      - VectorStore.get_by_ids 失败时抛异常
      - BM25 查询本身不失败（纯本地计算）
    """

    def test_vector_store_error_propagates(self) -> None:
        """VectorStore 失败时异常透传（Fail-Fast）"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(error=VectorStoreError("DB connection failed"))
        retriever = SparseRetriever(_make_settings(), bm25, store)

        with pytest.raises(VectorStoreError, match="DB connection failed"):
            retriever.retrieve(["test"], top_k=5)

    def test_bm25_empty_results_no_vector_store_call(self) -> None:
        """BM25 无结果时不调用 VectorStore"""
        bm25 = MockBM25Indexer(results=[])
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["nonexistent"], top_k=5)

        assert results == []
        # 无结果不应调用 VectorStore
        assert len(store.get_by_ids_calls) == 0


# ============================================================
# TestTraceIntegration — Trace 集成
# ============================================================

class TestTraceIntegration:
    """Trace 集成测试（2 个测试）

    知识点：TraceContext 使用
      - retrieve() 可选接受 trace 参数
      - trace 不为 None 时记录 sparse_retriever 阶段
      - 记录内容：keywords_count, bm25_result_count, result_count, duration
    """

    def test_trace_recorded_when_provided(self) -> None:
        """提供 trace 时记录 sparse_retriever 阶段"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        trace = TraceContext()
        retriever.retrieve(["python", "machine", "learning"], top_k=5, trace=trace)

        stages = trace.get_stages("sparse_retriever")
        assert len(stages) == 1
        stage = stages[0]
        assert stage.data["keywords_count"] == 3
        assert stage.data["bm25_result_count"] == 3
        assert stage.data["result_count"] == 3
        assert stage.data["bm25_duration_ms"] is not None
        assert stage.data["get_by_ids_duration_ms"] is not None
        assert stage.duration_ms is not None
        assert stage.duration_ms >= 0

    def test_no_trace_no_error(self) -> None:
        """不提供 trace 时不报错"""
        bm25 = MockBM25Indexer(results=_make_bm25_results())
        store = MockVectorStore(records=_make_vector_store_records())
        retriever = SparseRetriever(_make_settings(), bm25, store)

        # trace=None 应正常工作
        results = retriever.retrieve(["test"], trace=None)
        assert len(results) == 3


# ============================================================
# TestResultSorting — 结果排序
# ============================================================

class TestResultSorting:
    """结果排序测试（2 个测试）

    知识点：结果按 score 降序排列
      - BM25 query 返回已排序结果
      - 但 get_by_ids 可能打乱顺序
      - retrieve 显式排序保证正确性
    """

    def test_results_sorted_by_score_desc(self) -> None:
        """结果按 score 降序排列"""
        bm25 = MockBM25Indexer(results=[
            {"chunk_id": "c1", "score": 1.0},
            {"chunk_id": "c2", "score": 3.0},
            {"chunk_id": "c3", "score": 2.0},
        ])
        store = MockVectorStore(records=[
            {"id": "c2", "text": "text2", "metadata": {}},
            {"id": "c3", "text": "text3", "metadata": {}},
            {"id": "c1", "text": "text1", "metadata": {}},
        ])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)

        scores = [r.score for r in results]
        assert scores == [3.0, 2.0, 1.0]

    def test_stable_sort_by_chunk_id(self) -> None:
        """相同 score 时按 chunk_id 字典序排序"""
        bm25 = MockBM25Indexer(results=[
            {"chunk_id": "c3", "score": 1.0},
            {"chunk_id": "c1", "score": 1.0},
            {"id": "c2", "score": 1.0},  # 注意：缺少 chunk_id，应被跳过
        ])
        store = MockVectorStore(records=[
            {"id": "c1", "text": "text1", "metadata": {}},
            {"id": "c3", "text": "text3", "metadata": {}},
        ])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)

        # c2 缺少 chunk_id 被跳过，c1 和 c3 按字典序
        assert len(results) == 2
        assert results[0].chunk_id == "c1"
        assert results[1].chunk_id == "c3"


# ============================================================
# TestReadOnlyProperties — 只读属性
# ============================================================

class TestReadOnlyProperties:
    """只读属性测试（1 个测试）"""

    def test_properties_accessible(self) -> None:
        """bm25_indexer 和 vector_store 属性可访问"""
        bm25 = MockBM25Indexer(results=[])
        store = MockVectorStore(records=[])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        assert retriever.bm25_indexer is bm25
        assert retriever.vector_store is store
        assert retriever.bm25_indexer.num_docs == 10  # MockBM25Indexer 默认 N=10


# ============================================================
# TestEdgeCases — 边界情况
# ============================================================

class TestEdgeCases:
    """边界情况测试（2 个测试）"""

    def test_bm25_returns_ids_not_in_vector_store(self) -> None:
        """BM25 返回的 chunk_id 在 VectorStore 中找不到"""
        bm25 = MockBM25Indexer(results=[
            {"chunk_id": "existing_id", "score": 2.0},
            {"chunk_id": "missing_id", "score": 1.0},
        ])
        store = MockVectorStore(records=[
            {"id": "existing_id", "text": "found text", "metadata": {}},
            # missing_id 不在 VectorStore 中
        ])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=5)

        # 只返回能找到的
        assert len(results) == 1
        assert results[0].chunk_id == "existing_id"

    def test_missing_id_field_in_record(self) -> None:
        """VectorStore 返回的记录缺少 id 字段"""
        bm25 = MockBM25Indexer(results=[
            {"chunk_id": "chunk_0001", "score": 1.0},
        ])
        store = MockVectorStore(records=[
            {"text": "no id field", "metadata": {}},  # 缺少 id
        ])
        retriever = SparseRetriever(_make_settings(), bm25, store)

        results = retriever.retrieve(["test"], top_k=1)

        # 缺少 id 的记录被跳过
        assert len(results) == 0


# ============================================================
# TestBM25IndexerQuery — BM25Indexer.query() 新增方法测试
# ============================================================

class TestBM25IndexerQuery:
    """BM25Indexer.query() 方法测试（2 个测试）

    知识点：query() 是便捷接口，接受 List[str] 而非 dict[str, float]
    """

    def test_query_converts_keywords_to_term_freq(self) -> None:
        """query() 将关键词列表转换为词频 dict"""
        indexer = BM25Indexer(persist_path="/tmp/test_bm25_d3")
        # 构建一个简单索引
        from ingestion.embedding.sparse_encoder import SparseVector
        indexer.build([
            SparseVector(
                chunk_id="chunk_0001",
                doc_id="doc_1",
                terms={"python": 2.0, "machine": 1.0},
                doc_len=3,
            ),
            SparseVector(
                chunk_id="chunk_0002",
                doc_id="doc_2",
                terms={"python": 1.0, "learning": 2.0},
                doc_len=3,
            ),
        ])

        results = indexer.query(["python", "machine"], top_k=5)

        assert len(results) == 2
        assert all("chunk_id" in r and "score" in r for r in results)
        # chunk_0001 包含 python + machine，分数应更高
        assert results[0]["chunk_id"] == "chunk_0001"

    def test_query_empty_keywords_returns_empty(self) -> None:
        """空 keywords 返回空列表"""
        indexer = BM25Indexer(persist_path="/tmp/test_bm25_d3_empty")
        from ingestion.embedding.sparse_encoder import SparseVector
        indexer.build([
            SparseVector(
                chunk_id="chunk_0001",
                doc_id="doc_1",
                terms={"test": 1.0},
                doc_len=1,
            ),
        ])

        results = indexer.query([], top_k=5)
        assert results == []

