"""
CompositeEvaluator 单元测试 — H2: 组合评估器

测试策略：
  - Mock 多个 Evaluator 验证并行执行
  - 测试结果合并
  - 测试异常隔离
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from typing import Any

_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from libs.evaluator.base_evaluator import (
    BaseEvaluator,
    EvalResult,
    GroundTruth,
    RetrievedChunk,
)
from observability.evaluation.composite_evaluator import CompositeEvaluator


# ============================================================
# Mock Evaluator
# ============================================================

class MockEvaluator(BaseEvaluator):
    """Mock 评估器"""

    def __init__(self, name: str, metrics: dict[str, float]) -> None:
        self._name = name
        self._metrics = metrics

    def evaluate(
        self,
        query: str,
        retrieved_chunks: list[Any],
        generated_answer: str,
        ground_truth: Any,
        **kwargs: Any,
    ) -> EvalResult:
        return EvalResult(backend_name=self.backend_name, metrics=self._metrics)

    @property
    def backend_name(self) -> str:
        return self._name


class FailingEvaluator(BaseEvaluator):
    """会失败的 Mock 评估器"""

    def evaluate(self, *args: Any, **kwargs: Any) -> EvalResult:
        raise RuntimeError("评估失败")

    @property
    def backend_name(self) -> str:
        return "failing"


# ============================================================
# TestCompositeEvaluator — 组合评估器测试
# ============================================================

class TestCompositeEvaluator:
    """CompositeEvaluator 测试（5 个测试）"""

    def test_combines_metrics(self) -> None:
        """组合多个评估器的指标"""
        ev1 = MockEvaluator("eval1", {"hit_rate": 0.8})
        ev2 = MockEvaluator("eval2", {"faithfulness": 0.9})

        composite = CompositeEvaluator([ev1, ev2])
        result = composite.evaluate(
            "test query",
            [RetrievedChunk(id="c1", score=0.9, text="text")],
            "",
            GroundTruth(query="test", golden_ids=["c1"]),
        )

        assert "eval1.hit_rate" in result.metrics
        assert "eval2.faithfulness" in result.metrics
        assert result.metrics["eval1.hit_rate"] == 0.8
        assert result.metrics["eval2.faithfulness"] == 0.9

    def test_backend_name(self) -> None:
        """backend_name 为 composite"""
        composite = CompositeEvaluator([MockEvaluator("ev", {})])
        assert composite.backend_name == "composite"

    def test_failing_evaluator_isolated(self) -> None:
        """单个评估器失败不影响其他"""
        ev1 = MockEvaluator("good", {"hit_rate": 1.0})
        ev2 = FailingEvaluator()

        composite = CompositeEvaluator([ev1, ev2])
        result = composite.evaluate("q", [], "", GroundTruth())

        # ev1 的结果应包含
        assert "good.hit_rate" in result.metrics
        # ev2 失败不影响
        assert result.details["backends"].get("failing") is None

    def test_empty_evaluators_raises(self) -> None:
        """无 evaluator 时抛出 ValueError"""
        with pytest.raises(ValueError, match="至少一个"):
            CompositeEvaluator([])

    def test_create_composite_helper(self) -> None:
        """create_composite 辅助函数"""
        from observability.evaluation.composite_evaluator import create_composite
        composite = create_composite(["custom"])
        assert isinstance(composite, CompositeEvaluator)
        assert composite.backend_name == "composite"

