"""
CompositeEvaluator — 组合多个评估器并行执行

知识点：CompositeEvaluator 的设计
  - 组合模式：将多个 Evaluator 组合为一个
  - 并行执行：使用 ThreadPoolExecutor 并行运行多个评估后端
  - 汇总结果：合并各后端的 metrics 到一个 EvalResult
  - 面试考点："为什么用组合模式？" → 遵循开闭原则，新增后端不改已有代码
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from libs.evaluator.base_evaluator import (
    BaseEvaluator,
    EvalResult,
    GroundTruth,
    RetrievedChunk,
)
from typing import Any

logger = logging.getLogger(__name__)


class CompositeEvaluator(BaseEvaluator):
    """组合评估器 — 并行执行多个评估后端并汇总结果

    知识点：CompositeEvaluator 的使用场景
      - 配置驱动：settings.evaluation.backends: [ragas, custom]
      - 并行执行：I/O 密集（LLM 调用）时并行加速
      - 结果合并：metrics 字典合并，details 记录各后端结果
      - 面试考点："并行 vs 串行？" → 降低延迟（多个 LLM 调用可并行）

    异常隔离：
      - 单个 Evaluator 失败不影响其他
      - 失败的 Evaluator 记录 warning，不加入结果
    """

    def __init__(self, evaluators: list[BaseEvaluator]) -> None:
        """
        入参：
          - evaluators: BaseEvaluator 实例列表
        """
        if not evaluators:
            raise ValueError("CompositeEvaluator 需要至少一个 evaluator")
        self._evaluators = evaluators

    def evaluate(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        generated_answer: str,
        ground_truth: GroundTruth,
        **kwargs: Any,
    ) -> EvalResult:
        """并行执行所有评估器并汇总结果

        接口签名：evaluate(query, retrieved_chunks, generated_answer, ground_truth) -> EvalResult
        """
        all_metrics: dict[str, float] = {}
        all_details: dict[str, Any] = {"backends": {}}

        def _run_evaluator(evaluator: BaseEvaluator) -> tuple[str, EvalResult | None]:
            """运行单个评估器"""
            try:
                result = evaluator.evaluate(
                    query, retrieved_chunks, generated_answer, ground_truth, **kwargs
                )
                return (evaluator.backend_name, result)
            except Exception as e:
                logger.warning(
                    "CompositeEvaluator: %s 评估失败: %s",
                    evaluator.backend_name, e,
                )
                return (evaluator.backend_name, None)

        # 并行执行
        with ThreadPoolExecutor(max_workers=len(self._evaluators)) as executor:
            futures = {
                executor.submit(_run_evaluator, ev): ev
                for ev in self._evaluators
            }
            for future in as_completed(futures):
                backend_name, result = future.result()
                if result is not None:
                    # 合并 metrics（加前缀避免冲突）
                    for key, value in result.metrics.items():
                        all_metrics[f"{backend_name}.{key}"] = value
                    all_details["backends"][backend_name] = {
                        "metrics": result.metrics,
                        "details": result.details,
                    }

        return EvalResult(
            backend_name=self.backend_name,
            metrics=all_metrics,
            details=all_details,
        )

    @property
    def backend_name(self) -> str:
        return "composite"


def create_composite(backend_names: list[str]) -> CompositeEvaluator:
    """根据后端名列表创建 CompositeEvaluator

    接口签名：create_composite(backend_names: list[str]) -> CompositeEvaluator
    """
    from libs.evaluator.evaluator_factory import EvaluatorFactory

    evaluators = [EvaluatorFactory.create(name) for name in backend_names]
    return CompositeEvaluator(evaluators)

