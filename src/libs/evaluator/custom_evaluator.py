"""
自定义指标评估实现 — 轻量级工程指标（Hit Rate / MRR / Recall@K）

知识点：
  - CustomEvaluator 是什么：不依赖外部框架（如 Ragas/DeepEval），纯 Python 实现的评估器
  - 核心指标：Hit Rate, MRR, Recall@K — 都是检索质量指标
  - 用途：快速回归测试、上线前 Sanity Check、CI/CD 中的自动化质量门禁

指标定义（面试必须掌握）：

  Hit Rate（命中率）：
    - 定义：golden_id 是否出现在 Top-K 结果中
    - 取值：0（未命中）或 1（命中）
    - 公式：hit_rate = 1 if len(set(retrieved_ids[:K]) & set(golden_ids)) > 0 else 0
    - 特点：只关心有没有命中，不关心排名位置

  MRR (Mean Reciprocal Rank，平均倒数排名)：
    - 定义：第一个命中的 golden_id 在结果中的排名的倒数
    - 取值：0 到 1，越接近 1 表示命中位置越靠前
    - 公式：mrr = 1 / rank_of_first_hit
    - 特点：关心命中位置，排第 1 得 1.0，排第 3 得 0.333

  Recall@K（召回率）：
    - 定义：Top-K 结果中命中的 golden_ids 占所有 golden_ids 的比例
    - 取值：0 到 1，越接近 1 表示召回越全
    - 公式：recall = len(set(retrieved_ids[:K]) & set(golden_ids)) / len(golden_ids)
    - 特点：关心有多少 golden_id 被召回

  Precision@K（精确率）：
    - 定义：Top-K 结果中命中的数量占 Top-K 结果总数的比例
    - 取值：0 到 1，越接近 1 表示结果越精准
    - 公式：precision = len(set(retrieved_ids[:K]) & set(golden_ids)) / K
    - 特点：关心 Top-K 中有多少是正确的

面试考点：
  - "Hit Rate 和 MRR 的区别？" → Hit Rate 只判有无，MRR 还看排名位置
  - "MRR 为什么用倒数？" → 排名越靠前分数越高（第 1 名 = 1.0，第 2 名 = 0.5）
  - "Recall 和 Precision 的区别？" → Recall 看覆盖率（漏了多少），Precision 看准确率（错了多少）
  - "为什么用 CustomEvaluator 而非 Ragas？" → 轻量快速，不依赖 LLM，适合 CI/CD
"""

from __future__ import annotations

from typing import Any

from libs.evaluator.base_evaluator import (
    BaseEvaluator,
    EvalResult,
    EvaluatorError,
    GroundTruth,
    RetrievedChunk,
)


# ============================================================
# CustomEvaluator — 自定义轻量指标评估器
# ============================================================

class CustomEvaluator(BaseEvaluator):
    """自定义指标评估器 — 计算 Hit Rate / MRR / Recall@K / Precision@K

    接口签名：
      CustomEvaluator(top_k: int = 10)
      evaluate(query, retrieved_chunks, generated_answer, ground_truth) -> EvalResult

    知识点：CustomEvaluator 的定位
      - 轻量级：纯 Python，不依赖 LLM 或外部框架
      - 快速：O(K) 时间复杂度，毫秒级
      - 检索指标：只评估检索质量，不评估生成质量
      - 用途：CI/CD 质量门禁、回归测试、快速 Sanity Check

    与 RagasEvaluator 的区别：
      - CustomEvaluator：检索指标（hit_rate, mrr），不需要 LLM，快
      - RagasEvaluator：生成指标（faithfulness, relevancy），需要 LLM，慢
      - 面试考点："什么时候用 Custom？" → CI/CD 快速回归，不需要 LLM 调用

    top_k 参数：
      - 评估 Top-K 结果的指标（默认 K=10）
      - 只看前 K 条检索结果，后面的忽略
      - 面试考点："为什么只看 Top-K？" → 用户通常只看前几条结果
    """

    def __init__(self, top_k: int = 10) -> None:
        """初始化 CustomEvaluator

        接口签名：CustomEvaluator(top_k: int = 10)
        入参：
          - top_k: 评估 Top-K 结果的指标（默认 10）
        """
        if top_k <= 0:
            raise EvaluatorError(f"top_k 必须大于 0，当前值: {top_k}")
        self._top_k = top_k

    def evaluate(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        generated_answer: str,
        ground_truth: GroundTruth,
        **kwargs: Any,
    ) -> EvalResult:
        """计算检索质量指标

        接口签名：evaluate(query, retrieved_chunks, generated_answer, ground_truth) -> EvalResult
        入参：
          - query: 用户查询文本（CustomEvaluator 不使用，但保持接口一致）
          - retrieved_chunks: 检索返回的候选列表
          - generated_answer: LLM 生成的回答（CustomEvaluator 不使用，检索评估不需要）
          - ground_truth: 标准答案（使用 golden_ids 字段）
        出参：EvalResult（包含 hit_rate, mrr, recall@k, precision@k）

        计算流程：
          1. 从 retrieved_chunks 提取 id 列表
          2. 截取 Top-K
          3. 计算 hit_rate：golden_id 是否在 Top-K 中
          4. 计算 mrr：第一个命中 golden_id 的排名倒数
          5. 计算 recall@k：Top-K 中命中的 golden_ids 比例
          6. 计算 precision@k：Top-K 中命中的数量 / K
          7. 返回 EvalResult

        异常：
          - golden_ids 为空 → EvaluatorError（无法评估，没有标准答案）
          - top_k <= 0 → EvaluatorError（在 __init__ 中检查）

        面试考点：
          "generated_answer 在 CustomEvaluator 中有用吗？" → 没有，CustomEvaluator 只评估检索质量
          "如果 golden_ids 为空怎么办？" → 抛出 EvaluatorError，因为没有标准答案无法评估
        """
        # 校验 golden_ids
        if not ground_truth.golden_ids:
            raise EvaluatorError(
                "评估失败: ground_truth.golden_ids 为空，无法计算检索指标"
            )

        # 从 retrieved_chunks 提取 id 列表
        retrieved_ids = [chunk.id for chunk in retrieved_chunks]

        # 截取 Top-K
        top_k_ids = retrieved_ids[: self._top_k]
        k = min(self._top_k, len(top_k_ids))  # 实际 K（可能少于 top_k）

        # golden_ids 集合（用于集合运算）
        golden_set = set(ground_truth.golden_ids)

        # ============================================================
        # 计算 Hit Rate
        # ============================================================
        hit_rate = 1.0 if len(set(top_k_ids) & golden_set) > 0 else 0.0

        # ============================================================
        # 计算 MRR (Mean Reciprocal Rank)
        # ============================================================
        mrr = 0.0
        for rank, rid in enumerate(top_k_ids, start=1):
            if rid in golden_set:
                mrr = 1.0 / rank
                break  # 只取第一个命中的排名

        # ============================================================
        # 计算 Recall@K
        # ============================================================
        hit_count = len(set(top_k_ids) & golden_set)
        recall = hit_count / len(golden_set) if golden_set else 0.0

        # ============================================================
        # 计算 Precision@K
        # ============================================================
        precision = hit_count / k if k > 0 else 0.0

        # 构建指标字典
        metrics: dict[str, float] = {
            "hit_rate": round(hit_rate, 4),
            "mrr": round(mrr, 4),
            f"recall@{self._top_k}": round(recall, 4),
            f"precision@{self._top_k}": round(precision, 4),
        }

        # 构建详细信息
        details: dict[str, Any] = {
            "top_k": self._top_k,
            "actual_k": k,
            "retrieved_count": len(retrieved_chunks),
            "golden_count": len(ground_truth.golden_ids),
            "hit_count": hit_count,
            "first_hit_rank": int(1.0 / mrr) if mrr > 0 else None,
        }

        return EvalResult(
            backend_name=self.backend_name,
            metrics=metrics,
            details=details,
        )

    @property
    def backend_name(self) -> str:
        """返回后端名称"""
        return "custom"

    @property
    def top_k(self) -> int:
        """返回评估的 Top-K 值"""
        return self._top_k

