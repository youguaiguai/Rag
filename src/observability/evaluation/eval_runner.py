"""
EvalRunner — 评估执行器

知识点：EvalRunner 的设计
  - 读取 golden test set
  - 对每个 query 执行 HybridSearch + 评估
  - 汇总指标输出报告
  - 面试考点："评估流程？" → 准备测试集 → 逐条检索 → 评估 → 汇总
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from libs.evaluator.base_evaluator import (
    EvalResult,
    GroundTruth,
    RetrievedChunk,
)
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvalQueryResult:
    """单条 query 的评估结果"""
    query: str
    metrics: dict[str, float] = field(default_factory=dict)
    retrieved_count: int = 0
    hit: bool = False
    rank: int | None = None


@dataclass
class EvalReport:
    """评估报告"""
    total_queries: int = 0
    avg_metrics: dict[str, float] = field(default_factory=dict)
    per_query_results: list[EvalQueryResult] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """返回报告摘要"""
        lines = [
            "=== Evaluation Report ===",
            f"Total Queries: {self.total_queries}",
        ]
        for metric, value in self.avg_metrics.items():
            lines.append(f"  {metric}: {value:.4f}")
        return "\n".join(lines)


class EvalRunner:
    """评估执行器 — 运行评估并生成报告

    知识点：EvalRunner 的职责
      - 读取 golden test set
      - 调用 HybridSearch 检索
      - 调用 Evaluator 评估
      - 汇总结果生成报告
    """

    def __init__(
        self,
        hybrid_search: Any,
        evaluator: Any,
    ) -> None:
        """
        入参：
          - hybrid_search: HybridSearch 实例
          - evaluator: BaseEvaluator 实例
        """
        self._hybrid_search = hybrid_search
        self._evaluator = evaluator

    def run(self, test_set_path: str | Path) -> EvalReport:
        """运行评估

        接口签名：run(test_set_path) -> EvalReport
        入参：test_set_path — golden test set JSON 文件路径
        出参：EvalReport
        """
        test_set_path = Path(test_set_path)

        if not test_set_path.exists():
            raise FileNotFoundError(f"测试集不存在: {test_set_path}")

        # 读取测试集
        with open(test_set_path, "r", encoding="utf-8") as f:
            test_data = json.load(f)

        test_cases = test_data.get("test_cases", [])

        if not test_cases:
            return EvalReport(total_queries=0)

        # 逐条执行评估
        per_query_results: list[EvalQueryResult] = []
        all_metrics: dict[str, list[float]] = {}

        for case in test_cases:
            query = case.get("query", "")
            expected_ids = case.get("expected_chunk_ids", [])
            expected_sources = case.get("expected_sources", [])
            golden_answer = case.get("golden_answer", "")

            # 执行检索
            try:
                search_results = self._hybrid_search.search(query=query, top_k=10)
                retrieved_chunks = [
                    RetrievedChunk(
                        id=r.chunk_id,
                        score=r.score,
                        text=r.text,
                        metadata=r.metadata,
                    )
                    for r in search_results
                ]
            except Exception as e:
                logger.warning("EvalRunner: 检索失败 query=%r: %s", query, e)
                retrieved_chunks = []

            # 评估
            try:
                ground_truth = GroundTruth(
                    query=query,
                    golden_ids=expected_ids,
                    golden_answer=golden_answer,
                )
                eval_result = self._evaluator.evaluate(
                    query=query,
                    retrieved_chunks=retrieved_chunks,
                    generated_answer="",
                    ground_truth=ground_truth,
                )
                metrics = eval_result.metrics
            except Exception as e:
                logger.warning("EvalRunner: 评估失败 query=%r: %s", query, e)
                metrics = {}

            # 计算 hit
            retrieved_ids = [r.id for r in retrieved_chunks[:10]]
            hit = len(set(retrieved_ids) & set(expected_ids)) > 0
            rank = None
            for i, rid in enumerate(retrieved_ids, start=1):
                if rid in expected_ids:
                    rank = i
                    break

            per_query_results.append(EvalQueryResult(
                query=query,
                metrics=metrics,
                retrieved_count=len(retrieved_chunks),
                hit=hit,
                rank=rank,
            ))

            # 收集指标
            for key, value in metrics.items():
                if key not in all_metrics:
                    all_metrics[key] = []
                all_metrics[key].append(value)

        # 计算平均指标
        avg_metrics = {
            key: sum(values) / len(values) if values else 0.0
            for key, values in all_metrics.items()
        }

        return EvalReport(
            total_queries=len(test_cases),
            avg_metrics=avg_metrics,
            per_query_results=per_query_results,
            details={
                "evaluator": self._evaluator.backend_name,
                "test_set": str(test_set_path),
            },
        )

