"""
EvalRunner 单元测试 — H3: 评估执行器

测试策略：
  - Mock HybridSearch + Evaluator
  - 验证报告生成
  - 验证指标汇总
"""

from __future__ import annotations

import json
import pytest
import sys
from pathlib import Path
from typing import Any

_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from libs.evaluator.base_evaluator import BaseEvaluator, EvalResult, GroundTruth
from core.types import RetrievalResult
from observability.evaluation.eval_runner import EvalRunner, EvalReport


class MockEvaluator(BaseEvaluator):
    """Mock 评估器"""

    def evaluate(self, query: str = "", retrieved_chunks: Any = None, answer: str = "", gt: Any = None, **kw: Any) -> EvalResult:
        return EvalResult(
            backend_name=self.backend_name,
            metrics={"hit_rate": 1.0, "mrr": 0.5},
        )

    @property
    def backend_name(self) -> str:
        return "mock"


# ============================================================
# TestEvalRunner — 评估执行器测试
# ============================================================

class TestEvalRunner:
    """EvalRunner 测试（4 个测试）"""

    def test_run_generates_report(self, tmp_path: Path) -> None:
        """运行评估生成报告"""
        # 创建测试集
        test_set = {
            "test_cases": [
                {"query": "test query", "expected_chunk_ids": ["c1"]},
            ]
        }
        test_file = tmp_path / "test_set.json"
        test_file.write_text(json.dumps(test_set))

        # Mock HybridSearch
        mock_search = MagicMock()
        mock_search.search.return_value = [
            RetrievalResult(chunk_id="c1", score=0.9, text="text", metadata={}),
        ]

        evaluator = MockEvaluator()
        runner = EvalRunner(mock_search, evaluator)

        report = runner.run(test_file)

        assert isinstance(report, EvalReport)
        assert report.total_queries >= 1
        assert "hit_rate" in report.avg_metrics

    def test_report_summary(self) -> None:
        """报告摘要格式正确"""
        report = EvalReport(
            total_queries=5,
            avg_metrics={"hit_rate": 0.8, "mrr": 0.6},
        )
        summary = report.summary()
        assert "Total Queries: 5" in summary
        assert "hit_rate" in summary

    def test_missing_test_set_raises(self, tmp_path: Path) -> None:
        """测试集不存在时抛出 FileNotFoundError"""
        from observability.evaluation.eval_runner import EvalRunner
        runner = EvalRunner(MagicMock(), MockEvaluator())
        with pytest.raises(FileNotFoundError):
            runner.run(tmp_path / "nonexistent.json")

    def test_empty_test_set(self, tmp_path: Path) -> None:
        """空测试集返回空报告"""
        test_file = tmp_path / "empty.json"
        test_file.write_text(json.dumps({"test_cases": []}))

        runner = EvalRunner(MagicMock(), MockEvaluator())
        report = runner.run(test_file)

        assert report.total_queries == 0
        assert report.avg_metrics == {}


from unittest.mock import MagicMock  # noqa: E402

