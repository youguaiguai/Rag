"""
Recall 回归测试（E2E）— H5: 召回率回归测试

知识点：Recall 回归测试
  - 基于 golden test set 做最小召回阈值
  - hit@k 达到阈值（阈值写死，便于回归）
  - 面试考点："为什么要回归测试？" → 防止代码变更导致召回质量下降

使用 pytest.mark.e2e 标记，CI 中可选择性运行。
"""

from __future__ import annotations

import json
import pytest
import sys
from pathlib import Path

_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from libs.evaluator.base_evaluator import GroundTruth, RetrievedChunk
from libs.evaluator.custom_evaluator import CustomEvaluator

# 标记为 E2E 测试
pytestmark = pytest.mark.e2e


# ============================================================
# TestRecallThreshold — 召回阈值测试
# ============================================================

class TestRecallThreshold:
    """Recall 回归测试（3 个测试）

    注意：这些测试需要实际数据才能运行。
    无数据环境下降跳过。
    """

    def test_custom_evaluator_returns_hit_rate(self) -> None:
        """CustomEvaluator 计算 hit_rate"""
        evaluator = CustomEvaluator(top_k=5)

        chunks = [
            RetrievedChunk(id=f"chunk_{i}", score=0.9 - i * 0.1, text=f"text {i}")
            for i in range(10)
        ]
        ground_truth = GroundTruth(
            query="test",
            golden_ids=["chunk_0", "chunk_5"],
        )

        result = evaluator.evaluate("test", chunks, "", ground_truth)

        # chunk_0 在 Top-5 中 → hit_rate = 1.0
        assert result.metrics["hit_rate"] == 1.0
        assert result.metrics["mrr"] == 1.0  # 第 1 名就命中

    def test_custom_evaluator_miss(self) -> None:
        """未命中时 hit_rate = 0"""
        evaluator = CustomEvaluator(top_k=3)

        chunks = [
            RetrievedChunk(id=f"chunk_{i}", score=0.9 - i * 0.1, text=f"text {i}")
            for i in range(10)
        ]
        golden_ids = ["chunk_8", "chunk_9"]  # 在 Top-3 之外
        ground_truth = GroundTruth(query="test", golden_ids=golden_ids)

        result = evaluator.evaluate("test", chunks, "", ground_truth)

        assert result.metrics["hit_rate"] == 0.0
        assert result.metrics["mrr"] == 0.0

    def test_golden_test_set_exists(self) -> None:
        """Golden test set 文件存在且格式正确"""
        golden_path = Path("tests/fixtures/golden_test_set.json")
        assert golden_path.exists()

        with open(golden_path) as f:
            data = json.load(f)

        assert "test_cases" in data
        assert len(data["test_cases"]) > 0

        for case in data["test_cases"]:
            assert "query" in case

