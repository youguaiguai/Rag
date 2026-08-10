"""
Evaluator 模块 — 导出核心组件

可插拔 Evaluator 架构：
  BaseEvaluator（抽象基类） → CustomEvaluator（轻量检索指标）
                         → RagasEvaluator（H1 阶段实现，LLM-as-Judge 生成指标）

使用方式：
  from libs.evaluator import EvaluatorFactory, BaseEvaluator, GroundTruth, RetrievedChunk

  evaluator: BaseEvaluator = EvaluatorFactory.create("custom", top_k=10)
  result = evaluator.evaluate("查询", chunks, "", ground_truth)
  print(result.metrics)  # {'hit_rate': 0.8, 'mrr': 0.667, 'recall@10': 0.5, ...}
"""

from libs.evaluator.custom_evaluator import CustomEvaluator
from libs.evaluator.evaluator_factory import EvaluatorFactory

__all__ = [
    "BaseEvaluator",
    "EvalResult",
    "EvaluatorError",
    "EvaluatorFactory",
    "CustomEvaluator",
    "GroundTruth",
    "RetrievedChunk",
]

