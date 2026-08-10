"""
Evaluator 抽象基类 — 可插拔评估架构的核心

知识点：
  - Evaluator 是什么：对 RAG 系统的检索/生成质量进行量化评估
  - 评估维度：检索质量（hit_rate, mrr, recall）+ 生成质量（faithfulness, relevancy）
  - ABC (Abstract Base Class)：Python 标准库提供的抽象基类机制
  - 可插拔架构：上层代码只依赖 BaseEvaluator 接口，不关心底层用哪个评估框架
  - 工厂模式配合：EvaluatorFactory.create(settings) 根据 backend 创建具体实现

关键接口签名（面试必须掌握）：
  BaseEvaluator.evaluate(query, retrieved_chunks, generated_answer, ground_truth) -> EvalResult
    入参：
      - query: 用户查询文本
      - retrieved_chunks: 检索返回的候选列表（id + text + score）
      - generated_answer: LLM 生成的回答（可选，检索评估不需要）
      - ground_truth: 标准答案（golden answer / golden ids）
    出参：EvalResult（包含 metrics 字典 + 元信息）

  BaseEvaluator.backend_name -> str
    属性：返回当前评估后端名称（用于日志和报告）

设计原则：
  - 接口最小化：只暴露 evaluate() 一个核心方法 + 一个只读属性
  - 标准化输出：所有 Evaluator 返回 EvalResult，metrics 是 dict[str, float]
  - 面试考点："为什么要标准化输出？" → 不同后端的指标可以统一展示和对比

评估指标分类（面试考点）：
  检索指标（不需要 generated_answer）：
    - Hit Rate：golden_id 是否出现在 Top-K 结果中（0 或 1）
    - MRR (Mean Reciprocal Rank)：golden_id 在结果中的排名倒数（1/rank）
    - Recall@K：Top-K 中命中的 golden_ids 比例
    - Precision@K：Top-K 中命中结果的比例

  生成指标（需要 generated_answer，通常用 LLM-as-Judge）：
    - Faithfulness：回答是否忠于检索到的上下文（无幻觉）
    - Answer Relevancy：回答是否切题
    - Context Precision：检索的上下文是否精准

两段评估对应两段检索：
  检索评估 → 评估粗排 + 精排质量 → hit_rate, mrr, recall
  生成评估 → 评估最终回答质量 → faithfulness, relevancy
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class EvaluatorError(Exception):
    """Evaluator 评估异常

    知识点：为什么自定义异常？
      - 统一不同评估后端的异常类型
      - 上层代码只需 except EvaluatorError，不需要关心底层实现
      - 面试考点："异常转译模式" — 将底层异常包装为领域异常
    """
    pass


# ============================================================
# 数据契约 — 输入/输出类型
# ============================================================

@dataclass
class RetrievedChunk:
    """检索结果单元 — evaluate 的输入

    知识点：为什么用 dataclass 而非 dict？
      - 类型安全：id 是 str，score 是 float，有类型提示
      - IDE 补全：chunk.id, chunk.text 有补全
      - 与 RerankCandidate 字段对齐（id/score/text/metadata）

    接口签名：RetrievedChunk(id: str, score: float, text: str, metadata: dict)
    字段说明：
      - id: 检索结果 ID（chunk_id）
      - score: 检索分数（相似度/精排分数）
      - text: 检索结果文本
      - metadata: 元数据（source, page 等）
    """
    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GroundTruth:
    """标准答案 — evaluate 的输入

    知识点：GroundTruth 的设计
      - 同时支持检索评估和生成评估
      - golden_ids: 用于检索评估（hit_rate, mrr, recall）
      - golden_answer: 用于生成评估（faithfulness, answer_relevancy）
      - 两个字段都是可选的，根据评估指标决定使用哪个

    接口签名：GroundTruth(query: str, golden_ids: list[str], golden_answer: str)
    字段说明：
      - query: 原始查询文本（用于生成评估时的 prompt 构造）
      - golden_ids: 正确的 chunk_id 列表（用于 hit_rate, mrr, recall）
      - golden_answer: 标准答案文本（用于 faithfulness, answer_relevancy）
    """
    query: str = ""
    golden_ids: list[str] = field(default_factory=list)
    golden_answer: str = ""


@dataclass
class EvalResult:
    """评估结果 — evaluate 的输出

    知识点：标准化输出设计
      - metrics: 指标字典（指标名 → 分数），所有 Evaluator 统一格式
      - backend_name: 评估后端名称（用于报告展示）
      - details: 详细信息（可选，用于调试和深入分析）

    接口签名：EvalResult(backend_name: str, metrics: dict[str, float], details: dict)
    字段说明：
      - backend_name: 评估后端名称（如 'custom', 'ragas'）
      - metrics: 指标字典（如 {'hit_rate': 0.8, 'mrr': 0.667}）
      - details: 详细信息（如 per-query 结果，可选）

    面试考点："为什么用 dict 而非固定字段？"
      → 不同评估后端的指标不同（custom 输出 hit_rate/mrr，ragas 输出 faithfulness/relevancy）
      → 用 dict 可以灵活扩展，不需要改 EvalResult 类
    """
    backend_name: str
    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


# ============================================================
# BaseEvaluator 抽象基类
# ============================================================

class BaseEvaluator(ABC):
    """Evaluator 抽象基类 — 所有评估策略的统一接口

    接口签名：
      evaluate(query: str, retrieved_chunks: list[RetrievedChunk],
               generated_answer: str, ground_truth: GroundTruth) -> EvalResult
      backend_name -> str (property)

    使用方式（上层代码不关心具体评估后端）：
      evaluator: BaseEvaluator = EvaluatorFactory.create("custom")
      result = evaluator.evaluate("查询", chunks, "", ground_truth)
      print(result.metrics)  # {'hit_rate': 0.8, 'mrr': 0.667}

    知识点：为什么用 ABC？
      - ABC + @abstractmethod 强制子类实现 evaluate()，忘记实现会 TypeError
      - 面试考点："ABC 的作用？" → 编译期约束 + 类型安全 + 接口契约

    评估流程（面试考点）：
      1. 准备 golden_test_set（标准答案集）
      2. 对每个 query 执行 RAG 检索/生成
      3. 调用 evaluator.evaluate() 计算指标
      4. 汇总所有 query 的指标（平均值）
      5. 输出评估报告

    组合模式（面试考点）：
      - CompositeEvaluator 可以同时挂载多个 Evaluator
      - 并行执行各后端，汇总结果到一个综合报告
      - 配置示例：evaluation.backends: [ragas, custom_metrics]
    """

    @abstractmethod
    def evaluate(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        generated_answer: str,
        ground_truth: GroundTruth,
        **kwargs: Any,
    ) -> EvalResult:
        """对单条查询的检索/生成结果进行评估

        接口签名：evaluate(query, retrieved_chunks, generated_answer, ground_truth) -> EvalResult
        入参：
          - query: 用户查询文本
          - retrieved_chunks: 检索返回的候选列表
          - generated_answer: LLM 生成的回答（检索评估可传空字符串）
          - ground_truth: 标准答案（golden_ids 用于检索评估，golden_answer 用于生成评估）
        出参：EvalResult（包含 metrics 字典）
        异常：EvaluatorError — 评估失败

        知识点：单条评估 vs 批量评估
          - evaluate() 评估单条查询
          - 批量评估在上层循环调用 evaluate()，然后取平均
          - 面试考点："为什么不在 evaluate 里做批量？" → 单一职责，evaluate 只负责一条

        检索评估 vs 生成评估：
          - 检索评估：只需 retrieved_chunks + ground_truth.golden_ids → hit_rate, mrr
          - 生成评估：还需 generated_answer + ground_truth.golden_answer → faithfulness
        """
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """返回当前评估后端名称（用于日志和报告）

        接口签名：backend_name -> str (property)
        示例：'custom', 'ragas', 'deepeval'
        """
        ...

