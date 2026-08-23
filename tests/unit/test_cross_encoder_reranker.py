"""B7.8: Cross-Encoder Reranker 测试

测试结构：
  1. 初始化测试（3 个）
  2. rerank 行为测试（5 个）
  3. 默认 scorer 测试（2 个）
  4. 自定义 scorer 测试（2 个）
  5. fallback 测试（1 个）
  6. 工厂路由测试（1 个）
"""

from __future__ import annotations

import pytest
from core.settings import RerankSettings
from libs.reranker.base_reranker import BaseReranker, RerankCandidate
from libs.reranker.cross_encoder_reranker import CrossEncoderReranker, default_scorer
from libs.reranker.reranker_factory import RerankerFactory
from typing import Any


def make_candidate(id: str = "c1", score: float = 0.9, text: str = "测试文本") -> RerankCandidate:
    return RerankCandidate(id=id, score=score, text=text, metadata={"source": "doc.pdf"})


class TestCrossEncoderInit:

    def test_is_base_reranker(self):
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"))
        assert isinstance(r, BaseReranker)

    def test_backend_name(self):
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"))
        assert r.backend_name == "cross_encoder"

    def test_default_scorer_used(self):
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"))
        assert r._scorer is default_scorer


class TestCrossEncoderRerank:

    def test_rerank_empty_candidates(self):
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"))
        assert r.rerank("query", []) == []

    def test_rerank_single_candidate(self):
        """单条候选打分并返回"""
        def mock_scorer(q: str, d: str) -> float:
            return 0.85
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"), scorer=mock_scorer)
        c = make_candidate(id="c1", score=0.5, text="doc")
        result = r.rerank("query", [c])
        assert len(result) == 1
        assert result[0].score == 0.85

    def test_rerank_reorders_by_score(self):
        """按 Cross-Encoder 分数重排"""
        scores = {"doc1": 0.3, "doc2": 0.9}
        def mock_scorer(q: str, d: str) -> float:
            return scores.get(d, 0.0)
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"), scorer=mock_scorer)
        candidates = [
            make_candidate(id="c1", score=0.9, text="doc1"),
            make_candidate(id="c2", score=0.5, text="doc2"),
        ]
        result = r.rerank("query", candidates)
        assert result[0].id == "c2"  # doc2 得 0.9 > doc1 得 0.3
        assert result[1].id == "c1"

    def test_rerank_top_m_limit(self):
        """top_m 限制参与重排的候选数"""
        def mock_scorer(q: str, d: str) -> float:
            return 0.5
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder", top_m=2), scorer=mock_scorer)
        candidates = [make_candidate(id=f"c{i}", text=f"doc{i}") for i in range(5)]
        result = r.rerank("query", candidates)
        assert len(result) == 5
        # 前 2 个被重排（score=0.5），后 3 个保持原样
        assert result[0].score == 0.5
        assert result[2].score == 0.9  # 原始 score

    def test_rerank_preserves_metadata(self):
        """metadata 不变"""
        def mock_scorer(q: str, d: str) -> float:
            return 0.5
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"), scorer=mock_scorer)
        c = make_candidate(id="c1", text="doc")
        original_meta = dict(c.metadata)
        result = r.rerank("query", [c])
        assert result[0].metadata == original_meta


class TestDefaultScorer:

    def test_default_scorer_identical_text(self):
        """query == document → score = 1.0"""
        score = default_scorer("hello world", "hello world")
        assert score == 1.0

    def test_default_scorer_no_overlap(self):
        """无词汇重叠 → score = 0.0"""
        score = default_scorer("apple banana", "cat dog")
        assert score == 0.0


class TestCustomScorer:

    def test_custom_scorer_called(self):
        """自定义 scorer 被正确调用"""
        called: list[tuple[str, str]] = []
        def tracking_scorer(q: str, d: str) -> float:
            called.append((q, d))
            return 0.5
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"), scorer=tracking_scorer)
        r.rerank("my query", [make_candidate(id="c1", text="my doc")])
        assert len(called) == 1
        assert called[0] == ("my query", "my doc")

    def test_custom_scorer_deterministic(self):
        """同一 scorer 多次调用结果相同"""
        def mock_scorer(q: str, d: str) -> float:
            return hash(d) % 100 / 100.0
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"), scorer=mock_scorer)
        c = make_candidate(id="c1", text="doc")
        r1 = r.rerank("query", [c])
        c2 = make_candidate(id="c1", text="doc")
        r2 = r.rerank("query", [c2])
        assert r1[0].score == r2[0].score


class TestCrossEncoderFallback:

    def test_scorer_failure_returns_original_order(self):
        """scorer 抛异常时返回原始顺序"""
        def failing_scorer(q: str, d: str) -> float:
            raise RuntimeError("scorer failed")
        r = CrossEncoderReranker(RerankSettings(enabled=True, backend="cross_encoder"), scorer=failing_scorer)
        candidates = [
            make_candidate(id="c1", score=0.9, text="doc1"),
            make_candidate(id="c2", score=0.5, text="doc2"),
        ]
        result = r.rerank("query", candidates)
        # 返回原始顺序
        assert [c.id for c in result] == ["c1", "c2"]
        # score 不变
        assert result[0].score == 0.9


class TestCrossEncoderFactory:

    def test_factory_creates_cross_encoder(self):
        """backend=cross_encoder → CrossEncoderReranker"""
        settings = RerankSettings(enabled=True, backend="cross_encoder")
        r = RerankerFactory.create(settings)
        assert isinstance(r, CrossEncoderReranker)
        assert r.backend_name == "cross_encoder"

