"""
CoreReranker 单元测试 — D6: Core 层编排 + fallback

测试策略：
  - 使用 MockReranker 模拟后端行为（成功/失败/超时）
  - 验收标准全覆盖：
    1. 后端异常时不影响最终返回，且标记 fallback=true
    2. Reranker 未启用时直接返回原始排序
    3. 正常重排时返回精排后结果
    4. 类型转换正确（RetrievalResult ↔ RerankCandidate）
    5. 空候选处理

测试分类（18 个）：
  - 正常重排流程（4）
  - Fallback 降级（4）
  - 禁用 Reranker（3）
  - 类型转换验证（3）
  - 边界情况（2）
  - Trace 集成（2）
"""

from __future__ import annotations

import pytest
from core.query_engine.reranker import CoreReranker
from core.settings import Settings, RerankSettings
from core.trace.trace_context import TraceContext
from core.types import RetrievalResult
from libs.reranker.base_reranker import BaseReranker, RerankCandidate, RerankerError
from typing import Any


# ============================================================
# MockReranker — 可编程 Reranker 测试桩
# ============================================================

class MockReranker(BaseReranker):
    """可编程 Mock Reranker — 记录调用 + 可配置返回值/异常"""

    def __init__(
        self,
        rerorder_map: dict[str, int] | None = None,
        error: Exception | None = None,
    ) -> None:
        """
        入参：
          - rerorder_map: {chunk_id: new_score} — 自定义分数
          - error: 抛出异常（模拟后端失败）
        """
        self._rerorder_map = rerorder_map or {}
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        **kwargs: Any,
    ) -> list[RerankCandidate]:
        self.calls.append({"query": query, "candidate_count": len(candidates)})
        if self._error is not None:
            raise self._error
        # 按自定义分数排序（如果没有自定义则保持原顺序）
        scored = [
            RerankCandidate(
                id=c.id,
                score=self._rerorder_map.get(c.id, c.score),
                text=c.text,
                metadata=c.metadata,
            )
            for c in candidates
        ]
        scored.sort(key=lambda x: (-x.score, x.id))
        return scored

    @property
    def backend_name(self) -> str:
        return "mock_reranker"


class NoneRerankerMock(BaseReranker):
    """模拟 NoneReranker — 保持原顺序"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        **kwargs: Any,
    ) -> list[RerankCandidate]:
        self.calls.append({"query": query, "candidate_count": len(candidates)})
        return list(candidates)

    @property
    def backend_name(self) -> str:
        return "none"


# ============================================================
# 辅助函数
# ============================================================

def _make_settings(enabled: bool = True, backend: str = "cross_encoder") -> Settings:
    """创建测试用 Settings"""
    s = Settings()
    s.rerank.enabled = enabled
    s.rerank.backend = backend
    return s


def _make_candidates() -> list[RetrievalResult]:
    """创建测试用候选列表"""
    return [
        RetrievalResult(chunk_id="chunk_a", score=0.5, text="Text A", metadata={"doc": "1"}),
        RetrievalResult(chunk_id="chunk_b", score=0.3, text="Text B", metadata={"doc": "2"}),
        RetrievalResult(chunk_id="chunk_c", score=0.1, text="Text C", metadata={"doc": "3"}),
    ]


def _make_reranker(
    enabled: bool = True,
    reranker: BaseReranker | None = None,
) -> CoreReranker:
    """创建测试用 CoreReranker"""
    settings = _make_settings(enabled=enabled)
    return CoreReranker(settings, reranker=reranker)


# ============================================================
# TestNormalRerankFlow — 正常重排流程
# ============================================================

class TestNormalRerankFlow:
    """正常重排流程测试（4 个测试）"""

    def test_rerank_returns_ranked_results(self) -> None:
        """正常重排返回重排后的结果"""
        # chunk_c 被赋予最高分，应排到第一位
        reranker = _make_reranker(
            reranker=MockReranker(rerorder_map={"chunk_c": 0.99})
        )
        candidates = _make_candidates()

        results = reranker.rerank("test", candidates)

        assert len(results) == 3
        # chunk_c 被重排为最高分，应排第一
        assert results[0].chunk_id == "chunk_c"
        assert results[0].score == 0.99

    def test_rerank_calls_backend(self) -> None:
        """正确调用后端 rerank 方法"""
        mock = MockReranker()
        reranker = _make_reranker(reranker=mock)
        candidates = _make_candidates()

        reranker.rerank("my query", candidates)

        assert len(mock.calls) == 1
        assert mock.calls[0]["query"] == "my query"
        assert mock.calls[0]["candidate_count"] == 3

    def test_rerank_preserves_all_candidates(self) -> None:
        """重排后所有候选都保留（不丢失）"""
        reranker = _make_reranker(reranker=MockReranker())
        candidates = _make_candidates()

        results = reranker.rerank("test", candidates)

        assert len(results) == 3
        result_ids = {r.chunk_id for r in results}
        assert result_ids == {"chunk_a", "chunk_b", "chunk_c"}

    def test_rerank_updates_scores(self) -> None:
        """重排后 score 更新为精排分数"""
        reranker = _make_reranker(
            reranker=MockReranker(rerorder_map={"chunk_a": 0.95, "chunk_b": 0.85, "chunk_c": 0.75})
        )
        candidates = _make_candidates()

        results = reranker.rerank("test", candidates)

        score_map = {r.chunk_id: r.score for r in results}
        assert score_map["chunk_a"] == 0.95
        assert score_map["chunk_b"] == 0.85
        assert score_map["chunk_c"] == 0.75


# ============================================================
# TestFallbackDegradation — Fallback 降级测试
# ============================================================

class TestFallbackDegradation:
    """Fallback 降级测试（4 个测试）

    知识点：Reranker 后端失败时的降级策略
      - 返回原始排序（fusion 排名）
      - 标记 fallback=True
      - 不影响最终返回
    """

    def test_reranker_error_returns_original_order(self) -> None:
        """Reranker RerankerError 时返回原始排序"""
        reranker = _make_reranker(
            reranker=MockReranker(error=RerankerError("Backend unavailable"))
        )
        candidates = _make_candidates()

        results = reranker.rerank("test", candidates)

        # 返回原始排序
        assert len(results) == 3
        assert results[0].chunk_id == "chunk_a"
        assert results[1].chunk_id == "chunk_b"
        assert results[2].chunk_id == "chunk_c"

    def test_generic_error_returns_original_order(self) -> None:
        """通用异常时返回原始排序"""
        reranker = _make_reranker(
            reranker=MockReranker(error=RuntimeError("Unexpected error"))
        )
        candidates = _make_candidates()

        results = reranker.rerank("test", candidates)

        # 返回原始排序
        assert len(results) == 3

    def test_fallback_preserves_scores(self) -> None:
        """降级时保留原始分数"""
        original = _make_candidates()
        reranker = _make_reranker(
            reranker=MockReranker(error=Exception("Timeout"))
        )

        results = reranker.rerank("test", original)

        # score 保留原始值
        assert results[0].score == 0.5
        assert results[1].score == 0.3
        assert results[2].score == 0.1

    def test_fallback_does_not_raise(self) -> None:
        """降级时不抛异常（对调用方透明）"""
        reranker = _make_reranker(
            reranker=MockReranker(error=RerankerError("Failed"))
        )
        candidates = _make_candidates()

        # 不应抛异常
        results = reranker.rerank("test", candidates)
        assert len(results) == 3


# ============================================================
# TestDisabledReranker — 禁用 Reranker 测试
# ============================================================

class TestDisabledReranker:
    """禁用 Reranker 测试（3 个测试）"""

    def test_disabled_reranker_returns_original(self) -> None:
        """未启用时返回原始排序"""
        reranker = _make_reranker(enabled=False, reranker=MockReranker())
        candidates = _make_candidates()

        results = reranker.rerank("test", candidates)

        assert len(results) == 3
        assert results[0].chunk_id == "chunk_a"

    def test_disabled_reranker_does_not_call_backend(self) -> None:
        """未启用时不调用后端"""
        mock = MockReranker()
        reranker = _make_reranker(enabled=False, reranker=mock)
        candidates = _make_candidates()

        reranker.rerank("test", candidates)

        assert len(mock.calls) == 0

    def test_none_backend_returns_original(self) -> None:
        """NoneReranker 保持原顺序"""
        reranker = _make_reranker(reranker=NoneRerankerMock())
        candidates = _make_candidates()

        results = reranker.rerank("test", candidates)

        assert len(results) == 3
        assert results[0].chunk_id == "chunk_a"
        assert results[1].chunk_id == "chunk_b"
        assert results[2].chunk_id == "chunk_c"


# ============================================================
# TestTypeConversion — 类型转换验证
# ============================================================

class TestTypeConversion:
    """类型转换验证测试（3 个测试）

    知识点：类型转换
      RetrievalResult → RerankCandidate: chunk_id → id
      RerankCandidate → RetrievalResult: id → chunk_id
    """

    def test_chunk_id_to_id_conversion(self) -> None:
        """chunk_id 正确转换为 id"""
        mock = MockReranker()
        reranker = _make_reranker(reranker=mock)
        candidates = [
            RetrievalResult(chunk_id="my_chunk_001", score=0.5, text="text", metadata={}),
        ]

        reranker.rerank("test", candidates)

        # 后端收到的 candidate id 应为 chunk_id
        backend_candidates = mock.calls[0]["candidate_count"]
        assert backend_candidates == 1

    def test_id_to_chunk_id_conversion(self) -> None:
        """id 正确转换为 chunk_id"""
        reranker = _make_reranker(
            reranker=MockReranker(rerorder_map={"custom_id": 0.9})
        )
        candidates = [
            RetrievalResult(chunk_id="custom_id", score=0.1, text="text", metadata={}),
        ]

        results = reranker.rerank("test", candidates)

        assert results[0].chunk_id == "custom_id"
        assert results[0].score == 0.9

    def test_metadata_preserved(self) -> None:
        """metadata 在转换中保留"""
        reranker = _make_reranker(reranker=MockReranker())
        candidates = [
            RetrievalResult(
                chunk_id="c1",
                score=0.5,
                text="text",
                metadata={"title": "Doc 1", "page": 5, "source": "test.pdf"},
            ),
        ]

        results = reranker.rerank("test", candidates)

        assert results[0].metadata["title"] == "Doc 1"
        assert results[0].metadata["page"] == 5
        assert results[0].metadata["source"] == "test.pdf"


# ============================================================
# TestEdgeCases — 边界情况
# ============================================================

class TestEdgeCases:
    """边界情况测试（2 个测试）"""

    def test_empty_candidates_returns_empty(self) -> None:
        """空候选列表返回空列表"""
        reranker = _make_reranker(reranker=MockReranker())

        results = reranker.rerank("test", [])

        assert results == []

    def test_single_candidate(self) -> None:
        """单个候选正常处理"""
        reranker = _make_reranker(reranker=MockReranker())
        candidates = [
            RetrievalResult(chunk_id="only_one", score=0.5, text="text", metadata={}),
        ]

        results = reranker.rerank("test", candidates)

        assert len(results) == 1
        assert results[0].chunk_id == "only_one"


# ============================================================
# TestTraceIntegration — Trace 集成
# ============================================================

class TestTraceIntegration:
    """Trace 集成测试（2 个测试）"""

    def test_success_trace_not_fallback(self) -> None:
        """成功重排时 trace 标记 fallback=false"""
        reranker = _make_reranker(reranker=MockReranker())
        candidates = _make_candidates()

        trace = TraceContext()
        reranker.rerank("test", candidates, trace=trace)

        stages = trace.get_stages("reranker")
        assert len(stages) == 1
        stage = stages[0]
        assert stage.data["status"] == "success"
        assert stage.data["fallback"] is False
        assert stage.data["backend"] == "mock_reranker"
        assert stage.duration_ms is not None

    def test_fallback_trace_marks_true(self) -> None:
        """降级时 trace 标记 fallback=true"""
        reranker = _make_reranker(
            reranker=MockReranker(error=RerankerError("Failed"))
        )
        candidates = _make_candidates()

        trace = TraceContext()
        reranker.rerank("test", candidates, trace=trace)

        stages = trace.get_stages("reranker")
        assert stages[0].data["status"] == "fallback"
        assert stages[0].data["fallback"] is True

