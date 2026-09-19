"""
HybridSearch 集成测试 — D5: Dense + Sparse + RRF Fusion + Metadata 过滤

测试策略：
  - 使用 Mock 组件（MockQueryProcessor, MockDenseRetriever, MockSparseRetriever）测试完整流程
  - 也测试 RRF Fusion 单独逻辑
  - 验收标准全覆盖：
    1. 能返回 Top-K（包含 chunk 文本与 metadata）
    2. 支持 filters 参数进行过滤
    3. Dense/Sparse 任一路径失败时能降级到单路结果

测试分类（22 个）：
  - RRF Fusion 算法（7）
  - HybridSearch 完整流程（6）
  - 降级策略（4）
  - Metadata 过滤（3）
  - Trace 集成（2）
"""

from __future__ import annotations

import pytest
from core.query_engine.fusion import Fusion
from core.query_engine.hybrid_search import HybridSearch
from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import ProcessedQuery, RetrievalResult
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from libs.vector_store.base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
)
from typing import Any


# ============================================================
# MockQueryProcessor — 可编程 QueryProcessor 测试桩
# ============================================================

class MockQueryProcessor:
    """Mock QueryProcessor — 返回预设 ProcessedQuery"""

    def __init__(
        self,
        keywords: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._keywords = keywords or ["default", "keywords"]
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def process(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        trace: Any = None,
    ) -> ProcessedQuery:
        self.calls.append({"query": query, "filters": filters})
        if self._error is not None:
            raise self._error
        # 模拟真实 QueryProcessor：空查询抛 ValueError
        if not isinstance(query, str) or not query.strip():
            raise ValueError("查询不能为空")
        return ProcessedQuery(
            raw_query=query.strip(),
            keywords=self._keywords,
            filters=filters or {},
        )


# ============================================================
# MockDenseRetriever — 可编程 DenseRetriever 测试桩
# ============================================================

class MockDenseRetriever:
    """Mock DenseRetriever — 返回预设结果或异常"""

    def __init__(
        self,
        results: list[RetrievalResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._results = results or []
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        trace: Any = None,
    ) -> list[RetrievalResult]:
        self.calls.append({"query": query, "top_k": top_k, "filters": filters})
        if self._error is not None:
            raise self._error
        return list(self._results)


# ============================================================
# MockSparseRetriever — 可编程 SparseRetriever 测试桩
# ============================================================

class MockSparseRetriever:
    """Mock SparseRetriever — 返回预设结果或异常"""

    def __init__(
        self,
        results: list[RetrievalResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._results = results or []
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def retrieve(
        self,
        keywords: list[str],
        top_k: int = 10,
        trace: Any = None,
    ) -> list[RetrievalResult]:
        self.calls.append({"keywords": keywords, "top_k": top_k})
        if self._error is not None:
            raise self._error
        return list(self._results)


# ============================================================
# 辅助函数
# ============================================================

def _make_settings() -> Settings:
    """创建测试用 Settings"""
    s = Settings()
    s.retrieval.top_k_dense = 20
    s.retrieval.top_k_sparse = 20
    s.retrieval.top_k_final = 10
    return s


def _make_hybrid_search(
    dense_results: list[RetrievalResult] | None = None,
    sparse_results: list[RetrievalResult] | None = None,
    keywords: list[str] | None = None,
    dense_error: Exception | None = None,
    sparse_error: Exception | None = None,
) -> tuple[HybridSearch, MockQueryProcessor, MockDenseRetriever, MockSparseRetriever]:
    """创建测试用 HybridSearch 实例"""
    settings = _make_settings()
    processor = MockQueryProcessor(keywords=keywords or ["test", "query"])
    dense = MockDenseRetriever(results=dense_results, error=dense_error)
    sparse = MockSparseRetriever(results=sparse_results, error=sparse_error)
    fusion = Fusion(k=60)
    hybrid = HybridSearch(settings, processor, dense, sparse, fusion)
    return hybrid, processor, dense, sparse


# ============================================================
# TestRRFFusion — RRF Fusion 算法测试
# ============================================================

class TestRRFFusion:
    """RRF Fusion 算法测试（7 个测试）

    知识点：RRF 公式验证
      Score(d) = Σ 1/(k + rank_i(d))
      k 默认 60，排名从 1 开始
    """

    def test_fuse_empty_lists(self) -> None:
        """空输入返回空输出"""
        fusion = Fusion(k=60)
        assert fusion.fuse([]) == []

    def test_fuse_single_list(self) -> None:
        """单路结果直接透传（按原顺序）"""
        fusion = Fusion(k=60)
        results = [
            RetrievalResult(chunk_id="a", score=0.9, text="text_a", metadata={}),
            RetrievalResult(chunk_id="b", score=0.8, text="text_b", metadata={}),
        ]
        fused = fusion.fuse([results])
        # 单路 RRF：rank1 = 1/(60+1), rank2 = 1/(60+2)
        assert len(fused) == 2
        assert fused[0].chunk_id == "a"
        assert fused[1].chunk_id == "b"
        assert fused[0].score > fused[1].score

    def test_fuse_two_lists_basic(self) -> None:
        """两路结果正确融合"""
        fusion = Fusion(k=60)
        dense = [
            RetrievalResult(chunk_id="a", score=0.9, text="text_a", metadata={}),
            RetrievalResult(chunk_id="b", score=0.8, text="text_b", metadata={}),
        ]
        sparse = [
            RetrievalResult(chunk_id="b", score=2.0, text="text_b", metadata={}),
            RetrievalResult(chunk_id="c", score=1.5, text="text_c", metadata={}),
        ]
        fused = fusion.fuse([dense, sparse])
        # a: 1/(60+1) + 0        = 0.01639
        # b: 1/(60+2) + 1/(60+1) = 0.01613 + 0.01639 = 0.03252
        # c: 0        + 1/(60+2) = 0.01613
        # 排名：b > a > c
        assert len(fused) == 3
        assert fused[0].chunk_id == "b"  # 两路都出现，分数最高
        assert fused[1].chunk_id == "a"
        assert fused[2].chunk_id == "c"

    def test_fuse_preserves_text_and_metadata(self) -> None:
        """融合结果保留首次出现的 text 和 metadata"""
        fusion = Fusion(k=60)
        dense = [
            RetrievalResult(chunk_id="x", score=0.9, text="original text", metadata={"source": "dense"}),
        ]
        sparse = [
            RetrievalResult(chunk_id="x", score=1.0, text="different text", metadata={"source": "sparse"}),
        ]
        fused = fusion.fuse([dense, sparse])
        # 应保留首次出现（dense）的 text/metadata
        assert fused[0].text == "original text"
        assert fused[0].metadata["source"] == "dense"

    def test_fuse_top_k_truncation(self) -> None:
        """top_k 截断正确"""
        fusion = Fusion(k=60)
        results = [
            RetrievalResult(chunk_id=f"c{i}", score=1.0 - i * 0.1, text=f"text{i}", metadata={})
            for i in range(10)
        ]
        fused = fusion.fuse([results], top_k=5)
        assert len(fused) == 5

    def test_fuse_with_empty_list(self) -> None:
        """一路为空时，结果为另一路"""
        fusion = Fusion(k=60)
        dense = [
            RetrievalResult(chunk_id="a", score=0.9, text="text_a", metadata={}),
            RetrievalResult(chunk_id="b", score=0.8, text="text_b", metadata={}),
        ]
        fused = fusion.fuse([dense, []])
        assert len(fused) == 2
        assert fused[0].chunk_id == "a"
        assert fused[1].chunk_id == "b"

    def test_fuse_deterministic(self) -> None:
        """融合结果确定性（相同输入 → 相同输出）"""
        fusion = Fusion(k=60)
        dense = [
            RetrievalResult(chunk_id="a", score=0.9, text="t", metadata={}),
            RetrievalResult(chunk_id="b", score=0.8, text="t", metadata={}),
        ]
        sparse = [
            RetrievalResult(chunk_id="b", score=1.0, text="t", metadata={}),
            RetrievalResult(chunk_id="a", score=0.9, text="t", metadata={}),
        ]
        fused1 = fusion.fuse([dense, sparse])
        fused2 = fusion.fuse([dense, sparse])
        assert [r.chunk_id for r in fused1] == [r.chunk_id for r in fused2]
        assert [r.score for r in fused1] == [r.score for r in fused2]


# ============================================================
# TestHybridSearchFlow — HybridSearch 完整流程测试
# ============================================================

class TestHybridSearchFlow:
    """HybridSearch 完整流程测试（6 个测试）

    知识点：HybridSearch 完整流程
      query → process → parallel(dense + sparse) → fuse → filter → Top-K
    """

    def test_search_returns_top_k(self) -> None:
        """search 返回 Top-K 结果（包含 chunk 文本与 metadata）"""
        dense_results = [
            RetrievalResult(chunk_id="d1", score=0.95, text="Dense result 1", metadata={"doc": "d1"}),
            RetrievalResult(chunk_id="d2", score=0.85, text="Dense result 2", metadata={"doc": "d2"}),
        ]
        sparse_results = [
            RetrievalResult(chunk_id="s1", score=2.5, text="Sparse result 1", metadata={"doc": "s1"}),
            RetrievalResult(chunk_id="s2", score=1.8, text="Sparse result 2", metadata={"doc": "s2"}),
        ]
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=dense_results,
            sparse_results=sparse_results,
        )

        results = hybrid.search("test query", top_k=3)

        assert len(results) == 3
        assert all(isinstance(r, RetrievalResult) for r in results)
        assert all(r.text for r in results)  # 包含文本
        assert all(r.metadata for r in results)  # 包含 metadata

    def test_search_calls_all_components(self) -> None:
        """search 正确调用所有组件"""
        dense_results = [
            RetrievalResult(chunk_id="d1", score=0.9, text="t", metadata={}),
        ]
        sparse_results = [
            RetrievalResult(chunk_id="s1", score=2.0, text="t", metadata={}),
        ]
        hybrid, processor, dense, sparse = _make_hybrid_search(
            dense_results=dense_results,
            sparse_results=sparse_results,
            keywords=["test", "query"],
        )

        hybrid.search("my test query", top_k=5)

        # QueryProcessor 被调用
        assert len(processor.calls) == 1
        assert processor.calls[0]["query"] == "my test query"

        # DenseRetriever 被调用（传入 raw_query）
        assert len(dense.calls) == 1
        assert dense.calls[0]["query"] == "my test query"
        assert dense.calls[0]["top_k"] == 20  # settings.retrieval.top_k_dense

        # SparseRetriever 被调用（传入 keywords）
        assert len(sparse.calls) == 1
        assert sparse.calls[0]["keywords"] == ["test", "query"]

    def test_search_top_k_truncation(self) -> None:
        """search 最终结果按 top_k 截断"""
        dense_results = [
            RetrievalResult(chunk_id=f"d{i}", score=0.9 - i * 0.01, text=f"text{i}", metadata={})
            for i in range(15)
        ]
        sparse_results = [
            RetrievalResult(chunk_id=f"s{i}", score=2.0 - i * 0.1, text=f"text{i}", metadata={})
            for i in range(15)
        ]
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=dense_results,
            sparse_results=sparse_results,
        )

        results = hybrid.search("test", top_k=5)
        assert len(results) == 5

    def test_search_results_have_fused_scores(self) -> None:
        """融合结果的 score 是 RRF 分数而非原始分数"""
        dense_results = [
            RetrievalResult(chunk_id="a", score=0.99, text="t", metadata={}),
        ]
        sparse_results = [
            RetrievalResult(chunk_id="b", score=5.0, text="t", metadata={}),
        ]
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=dense_results,
            sparse_results=sparse_results,
        )

        results = hybrid.search("test", top_k=10)

        # RRF 分数应小于 1（1/(60+1) ≈ 0.016）
        for r in results:
            assert r.score < 1.0
            assert r.score > 0.0

    def test_search_empty_query_returns_empty(self) -> None:
        """空查询返回空结果"""
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=[RetrievalResult(chunk_id="x", score=0.9, text="t", metadata={})],
            sparse_results=[RetrievalResult(chunk_id="y", score=1.0, text="t", metadata={})],
        )

        results = hybrid.search("", top_k=5)
        assert results == []

    def test_search_passes_filters_to_dense_retriever(self) -> None:
        """filters 参数传递给 DenseRetriever"""
        hybrid, _, dense, _ = _make_hybrid_search(
            dense_results=[],
            sparse_results=[],
        )

        filters = {"doc_type": "pdf"}
        hybrid.search("test", top_k=5, filters=filters)

        assert dense.calls[0]["filters"] == filters


# ============================================================
# TestDegradationStrategy — 降级策略测试
# ============================================================

class TestDegradationStrategy:
    """降级策略测试（4 个测试）

    知识点：HybridSearch 降级策略
      - Dense 失败 → 返回 Sparse 结果
      - Sparse 失败 → 返回 Dense 结果
      - 两者都失败 → 抛异常
    """

    def test_dense_failure_falls_back_to_sparse(self) -> None:
        """Dense 失败时降级到 Sparse 结果"""
        sparse_results = [
            RetrievalResult(chunk_id="s1", score=2.0, text="Sparse only", metadata={"src": "sparse"}),
            RetrievalResult(chunk_id="s2", score=1.5, text="Sparse 2", metadata={"src": "sparse"}),
        ]
        hybrid, _, _, _ = _make_hybrid_search(
            dense_error=EmbeddingError("API failed"),
            sparse_results=sparse_results,
        )

        results = hybrid.search("test", top_k=5)

        assert len(results) == 2
        assert all(r.metadata.get("src") == "sparse" for r in results)

    def test_sparse_failure_falls_back_to_dense(self) -> None:
        """Sparse 失败时降级到 Dense 结果"""
        dense_results = [
            RetrievalResult(chunk_id="d1", score=0.95, text="Dense only", metadata={"src": "dense"}),
            RetrievalResult(chunk_id="d2", score=0.85, text="Dense 2", metadata={"src": "dense"}),
        ]
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=dense_results,
            sparse_error=Exception("BM25 index missing"),
        )

        results = hybrid.search("test", top_k=5)

        assert len(results) == 2
        assert all(r.metadata.get("src") == "dense" for r in results)

    def test_both_failure_raises_error(self) -> None:
        """两者都失败时抛异常"""
        hybrid, _, _, _ = _make_hybrid_search(
            dense_error=EmbeddingError("Dense failed"),
            sparse_error=Exception("Sparse failed"),
        )

        with pytest.raises(RuntimeError, match="混合检索失败"):
            hybrid.search("test", top_k=5)

    def test_degradation_records_trace_mode(self) -> None:
        """降级时 trace 记录正确的 mode"""
        hybrid, _, dense, _ = _make_hybrid_search(
            dense_error=RuntimeError("Dense unavailable"),
            sparse_results=[
                RetrievalResult(chunk_id="s1", score=1.0, text="t", metadata={}),
            ],
        )

        trace = TraceContext()
        hybrid.search("test", top_k=5, trace=trace)

        stages = trace.get_stages("hybrid_search")
        assert len(stages) == 1
        assert stages[0].data["mode"] == "sparse_only"


# ============================================================
# TestMetadataFiltering — Metadata 过滤测试
# ============================================================

class TestMetadataFiltering:
    """Metadata 过滤测试（3 个测试）

    知识点：metadata 过滤逻辑
      - filters 中所有条件必须同时满足（AND 逻辑）
      - 精确匹配（==）
      - 后置过滤兜底
    """

    def test_filters_applied_post_fusion(self) -> None:
        """filters 在融合后应用"""
        dense_results = [
            RetrievalResult(chunk_id="d1", score=0.9, text="PDF doc", metadata={"doc_type": "pdf"}),
            RetrievalResult(chunk_id="d2", score=0.8, text="MD doc", metadata={"doc_type": "md"}),
        ]
        sparse_results = [
            RetrievalResult(chunk_id="s1", score=2.0, text="PDF sparse", metadata={"doc_type": "pdf"}),
            RetrievalResult(chunk_id="s2", score=1.5, text="HTML sparse", metadata={"doc_type": "html"}),
        ]
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=dense_results,
            sparse_results=sparse_results,
        )

        results = hybrid.search("test", top_k=10, filters={"doc_type": "pdf"})

        # 只有 doc_type=pdf 的结果
        assert all(r.metadata.get("doc_type") == "pdf" for r in results)
        chunk_ids = {r.chunk_id for r in results}
        assert chunk_ids == {"d1", "s1"}

    def test_multiple_filter_conditions(self) -> None:
        """多个 filter 条件（AND 逻辑）"""
        results_data = [
            {"id": "c1", "doc_type": "pdf", "collection": "default"},
            {"id": "c2", "doc_type": "pdf", "collection": "other"},
            {"id": "c3", "doc_type": "md", "collection": "default"},
        ]
        all_results = [
            RetrievalResult(chunk_id=r["id"], score=0.9, text="t", metadata={"doc_type": r["doc_type"], "collection": r["collection"]})
            for r in results_data
        ]
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=all_results[:1],
            sparse_results=all_results[1:],
        )

        results = hybrid.search("test", top_k=10, filters={"doc_type": "pdf", "collection": "default"})

        assert len(results) == 1
        assert results[0].chunk_id == "c1"

    def test_no_filters_returns_all(self) -> None:
        """无 filters 时返回所有融合结果"""
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=[
                RetrievalResult(chunk_id="d1", score=0.9, text="t", metadata={"doc_type": "pdf"}),
            ],
            sparse_results=[
                RetrievalResult(chunk_id="s1", score=2.0, text="t", metadata={"doc_type": "md"}),
            ],
        )

        results = hybrid.search("test", top_k=10)

        # 两种 doc_type 的结果都返回
        assert len(results) == 2


# ============================================================
# TestTraceIntegration — Trace 集成测试
# ============================================================

class TestTraceIntegration:
    """Trace 集成测试（2 个测试）"""

    def test_trace_records_hybrid_search_stage(self) -> None:
        """trace 记录 hybrid_search 阶段"""
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=[
                RetrievalResult(chunk_id="d1", score=0.9, text="t", metadata={}),
            ],
            sparse_results=[
                RetrievalResult(chunk_id="s1", score=1.0, text="t", metadata={}),
            ],
        )

        trace = TraceContext()
        hybrid.search("test query", top_k=5, trace=trace)

        stages = trace.get_stages("hybrid_search")
        assert len(stages) == 1
        stage = stages[0]
        assert stage.data["query"] == "test query"
        assert stage.data["mode"] == "fused"  # 两者都成功
        assert stage.data["dense_count"] == 1
        assert stage.data["sparse_count"] == 1
        assert stage.data["final_count"] == 2
        assert stage.duration_ms is not None

    def test_trace_records_degraded_mode(self) -> None:
        """降级模式被 trace 记录"""
        hybrid, _, _, _ = _make_hybrid_search(
            dense_results=[
                RetrievalResult(chunk_id="d1", score=0.9, text="t", metadata={}),
            ],
            sparse_error=Exception("Sparse down"),
        )

        trace = TraceContext()
        hybrid.search("test", top_k=5, trace=trace)

        stages = trace.get_stages("hybrid_search")
        assert stages[0].data["mode"] == "dense_only"

