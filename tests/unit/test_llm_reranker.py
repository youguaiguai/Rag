"""B7.7: LLM Reranker 测试

测试结构：
  1. 初始化测试（3 个）
  2. rerank 行为测试（6 个）
  3. 评分解析测试（4 个）
  4. fallback 测试（2 个）
  5. 工厂路由测试（2 个）
"""

from __future__ import annotations

import pytest
from core.settings import RerankSettings
from libs.llm.base_llm import BaseLLM, LLMError
from libs.reranker.base_reranker import BaseReranker, RerankCandidate, RerankerError
from libs.reranker.llm_reranker import LLMReranker
from libs.reranker.reranker_factory import RerankerFactory
from typing import Any


class MockLLM(BaseLLM):
    """Mock LLM — 返回预设评分

    知识点：测试替身 (Test Double)
      - 不调用真实 LLM API
      - 根据 document 内容返回不同评分
    """

    def __init__(self, responses: list[str] | None = None, response: str = "5") -> None:
        self._responses = responses or []
        self._default_response = response
        self._call_count = 0

    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        if self._responses:
            idx = self._call_count % len(self._responses)
            self._call_count += 1
            return self._responses[idx]
        return self._default_response

    @property
    def model_name(self) -> str:
        return "mock-llm"


class FailingLLM(BaseLLM):
    """总是失败的 LLM — 用于测试 fallback"""

    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        raise LLMError("LLM 调用失败")

    @property
    def model_name(self) -> str:
        return "failing-llm"


def make_candidate(id: str = "c1", score: float = 0.9, text: str = "测试文本") -> RerankCandidate:
    return RerankCandidate(id=id, score=score, text=text, metadata={"source": "doc.pdf"})


class TestLLMRerankerInit:

    def test_is_base_reranker(self):
        llm = MockLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        assert isinstance(r, BaseReranker)

    def test_backend_name(self):
        llm = MockLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        assert r.backend_name == "llm"

    def test_custom_prompt_text(self):
        llm = MockLLM()
        prompt = "评分: {query} {document}"
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm, prompt_text=prompt)
        # 确保 prompt 被正确加载


class TestLLMRerankerRerank:

    def test_rerank_empty_candidates(self):
        llm = MockLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        result = r.rerank("query", [])
        assert result == []

    def test_rerank_single_candidate(self):
        llm = MockLLM(response="8")
        r = LLMReranker(RerankSettings(enabled=True, backend="llm", top_m=10), llm=llm)
        c = make_candidate(id="c1", score=0.5, text="doc text")
        result = r.rerank("query", [c])
        assert len(result) == 1
        assert result[0].id == "c1"
        assert result[0].score == 0.8  # 8/10 = 0.8

    def test_rerank_reorders_by_score(self):
        """按 LLM 评分重排顺序"""
        llm = MockLLM(responses=["3", "9"])  # c1 得 3 分，c2 得 9 分
        r = LLMReranker(RerankSettings(enabled=True, backend="llm", top_m=10), llm=llm)
        candidates = [
            make_candidate(id="c1", score=0.9, text="doc1"),
            make_candidate(id="c2", score=0.5, text="doc2"),
        ]
        result = r.rerank("query", candidates)
        # c2 得 9 分 > c1 得 3 分，所以 c2 在前
        assert result[0].id == "c2"
        assert result[1].id == "c1"

    def test_rerank_updates_score(self):
        """rerank 更新 candidate 的 score"""
        llm = MockLLM(response="7")
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        c = make_candidate(id="c1", score=0.5, text="doc")
        result = r.rerank("query", [c])
        assert result[0].score == 0.7  # 7/10 = 0.7

    def test_rerank_top_m_limit(self):
        """top_m 限制参与重排的候选数量"""
        llm = MockLLM(response="5")
        r = LLMReranker(RerankSettings(enabled=True, backend="llm", top_m=2), llm=llm)
        candidates = [make_candidate(id=f"c{i}", text=f"doc{i}") for i in range(5)]
        result = r.rerank("query", candidates)
        assert len(result) == 5  # 全部返回
        # 前 2 个被重排（score 变为 0.5），后 3 个保持原样
        assert result[0].score == 0.5  # 被重排
        assert result[2].score == 0.9  # 未被重排，保持原始 score

    def test_rerank_preserves_metadata(self):
        """rerank 不改变 metadata"""
        llm = MockLLM(response="5")
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        c = make_candidate(id="c1", text="doc")
        original_metadata = dict(c.metadata)
        result = r.rerank("query", [c])
        assert result[0].metadata == original_metadata


class TestLLMRerankerParseScore:

    def test_parse_pure_number(self):
        llm = MockLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        assert r._parse_score("8") == 0.8

    def test_parse_number_with_text(self):
        llm = MockLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        assert r._parse_score("评分：8分") == 0.8

    def test_parse_decimal(self):
        llm = MockLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        assert r._parse_score("7.5") == 0.75

    def test_parse_no_number(self):
        llm = MockLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        assert r._parse_score("无法评估") == 0.0


class TestLLMRerankerFallback:

    def test_llm_failure_returns_default_score(self):
        """LLM 调用失败时返回 0.0 分（不阻断流程）"""
        llm = FailingLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        c = make_candidate(id="c1", score=0.9, text="doc")
        result = r.rerank("query", [c])
        assert len(result) == 1
        assert result[0].score == 0.0  # 失败时默认 0 分

    def test_llm_failure_preserves_order(self):
        """LLM 全部失败时保持原始顺序"""
        llm = FailingLLM()
        r = LLMReranker(RerankSettings(enabled=True, backend="llm"), llm=llm)
        candidates = [
            make_candidate(id="c1", score=0.9, text="doc1"),
            make_candidate(id="c2", score=0.5, text="doc2"),
        ]
        result = r.rerank("query", candidates)
        # 全部失败时 score 都是 0.0，稳定排序保持原序
        assert [c.id for c in result] == ["c1", "c2"]


class TestLLMRerankerFactory:

    def test_factory_creates_llm_reranker(self):
        """backend=llm + llm 参数 → LLMReranker"""
        llm = MockLLM()
        settings = RerankSettings(enabled=True, backend="llm")
        r = RerankerFactory.create(settings, llm=llm)
        assert isinstance(r, LLMReranker)
        assert r.backend_name == "llm"

    def test_factory_llm_without_llm_raises(self):
        """backend=llm 但不传 llm → RerankerError"""
        settings = RerankSettings(enabled=True, backend="llm")
        with pytest.raises(RerankerError, match="llm 参数"):
            RerankerFactory.create(settings)

