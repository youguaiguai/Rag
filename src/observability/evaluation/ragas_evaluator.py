"""
RagasEvaluator — 封装 Ragas 框架的评估器

知识点：RagasEvaluator 的设计
  - 封装 Ragas 框架，实现 BaseEvaluator 接口
  - 支持指标：Faithfulness, Answer Relevancy, Context Precision
  - 优雅降级：Ragas 未安装时抛出明确的 ImportError
  - 面试考点："优雅降级 vs 直接崩溃？" → 明确错误提示 > 难以调试的失败
"""

from __future__ import annotations

from libs.evaluator.base_evaluator import (
    BaseEvaluator,
    EvalResult,
    EvaluatorError,
    GroundTruth,
    RetrievedChunk,
)
from typing import Any


class RagasEvaluator(BaseEvaluator):
    """Ragas 评估器 — 使用 Ragas 框架评估 RAG 质量

    知识点：RagasEvaluator 的定位
      - 生成质量评估：faithfulness, answer_relevancy, context_precision
      - 需要 LLM：Ragas 使用 LLM-as-Judge 评估生成质量
      - 比 CustomEvaluator 重：需要 LLM 调用，慢但更全面
      - 面试考点："什么时候用 Ragas？" → 需要评估生成质量（回答是否忠于上下文）

    优雅降级：
      - Ragas 未安装 → ImportError 提示安装
      - LLM 不可用 → EvaluatorError 提示检查配置
    """

    def __init__(self, llm: Any = None, top_k: int = 10) -> None:
        """
        入参：
          - llm: LLM 实例（可选，Ragas 默认使用 OpenAI）
          - top_k: 评估 Top-K 结果
        """
        self._llm = llm
        self._top_k = top_k
        self._verify_ragas_installed()

    @staticmethod
    def _verify_ragas_installed() -> None:
        """检查 Ragas 是否已安装

        知识点：延迟验证
          - 不在模块导入时检查（避免未使用 Ragas 时也报错）
          - 在实例化时检查（只有真正使用时才验证）
        """
        try:
            import ragas  # noqa: F401
        except ImportError:
            raise ImportError(
                "RagasEvaluator 需要 ragas 包。请运行：\n"
                "  pip install ragas\n"
                "或者在项目中添加 ragas 依赖。"
            )

    def evaluate(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        generated_answer: str,
        ground_truth: GroundTruth,
        **kwargs: Any,
    ) -> EvalResult:
        """使用 Ragas 评估

        接口签名：evaluate(query, retrieved_chunks, generated_answer, ground_truth) -> EvalResult
        """
        try:
            from ragas import evaluate as ragas_evaluate
            from ragas.metrics import faithfulness, answer_relevancy, context_precision
            from datasets import Dataset
        except ImportError as e:
            raise EvaluatorError(f"Ragas 导入失败: {e}")

        # 准备 Ragas 数据格式
        contexts = [chunk.text for chunk in retrieved_chunks[: self._top_k]]

        data = {
            "question": [query],
            "answer": [generated_answer or ""],
            "contexts": [contexts],
        }

        # 如果有 golden_answer，加入 reference
        if ground_truth.golden_answer:
            data["ground_truth"] = [ground_truth.golden_answer]

        dataset = Dataset.from_dict(data)

        # 选择指标
        metrics = [faithfulness, answer_relevancy, context_precision]

        # 执行评估
        try:
            result = ragas_evaluate(dataset, metrics=metrics)
            metrics_dict = {
                "faithfulness": float(result.get("faithfulness", 0.0) or 0.0),
                "answer_relevancy": float(result.get("answer_relevancy", 0.0) or 0.0),
                "context_precision": float(result.get("context_precision", 0.0) or 0.0),
            }
        except Exception as e:
            raise EvaluatorError(f"Ragas 评估失败: {e}")

        return EvalResult(
            backend_name=self.backend_name,
            metrics=metrics_dict,
            details={"contexts_count": len(contexts), "top_k": self._top_k},
        )

    @property
    def backend_name(self) -> str:
        return "ragas"

