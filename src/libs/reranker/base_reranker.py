"""
Reranker 抽象基类 — 可插拔架构的核心

知识点：
  - Reranker 是什么：对检索结果进行精排重排序，提升 Top-K 结果的精准度
  - 两段式检索架构：粗排（Hybrid Search 召回 Top-M） → 精排（Reranker 重排 Top-K）
  - ABC (Abstract Base Class)：Python 标准库提供的抽象基类机制
  - 可插拔架构：上层代码只依赖 BaseReranker 接口，不关心底层用的是哪种重排模型
  - 工厂模式配合：RerankerFactory.create(settings) 根据 backend 字段创建具体实现

关键接口签名（面试必须掌握）：
  BaseReranker.rerank(query: str, candidates: list[RerankCandidate]) -> list[RerankCandidate]
    入参：
      - query: 用户查询文本
      - candidates: 粗排返回的候选列表（已按相似度排序）
    出参：重排后的候选列表（按精排分数排序）
    异常：子类实现中可能抛出 RerankerError

  BaseReranker.backend_name -> str
    属性：返回当前重排后端名称（用于日志和追踪）

设计原则：
  - 接口最小化：只暴露 rerank() 一个核心方法 + 一个只读属性
  - 输入输出同类型：candidates 和返回值都是 list[RerankCandidate]，只是顺序和 score 不同
  - NoneReranker 默认回退：backend=none 时不改变排序，保证系统始终可用

面试考点：
  - "为什么要 Rerank？" → 粗排用速度换覆盖率（BM25+Dense），精排用质量换速度（CrossEncoder）
  - "NoneReranker 的作用？" → 默认回退，Reranker 失败或未启用时保持原排序
  - "CrossEncoder vs Bi-Encoder？" → CrossEncoder 联合编码精度高但慢；Bi-Encoder 分离编码快但精度低
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class RerankerError(Exception):
    """Reranker 重排异常

    知识点：为什么自定义异常？
      - 统一不同重排后端的异常类型
      - 上层代码只需 except RerankerError，不需要关心底层实现
      - D6 阶段的 fallback 逻辑会捕获此异常，回退到 fusion 排名
      - 面试考点："异常转译模式" — 将底层异常包装为领域异常
    """
    pass


# ============================================================
# 数据契约 — 输入/输出类型
# ============================================================

@dataclass
class RerankCandidate:
    """重排候选 — rerank 的输入输出单元

    知识点：为什么用 dataclass 而非 dict？
      - 类型安全：id 是 str，score 是 float，有类型提示
      - IDE 补全：candidate.id, candidate.text 有补全
      - 通用性：与 D2 的 RetrievalResult 字段对齐（id/score/text/metadata）

    接口签名：RerankCandidate(id: str, score: float, text: str, metadata: dict)
    字段说明：
      - id: 候选记录 ID（chunk_id）
      - score: 原始检索分数（粗排分数），重排后会被更新为精排分数
      - text: 候选文本（送入 CrossEncoder/LLM 进行精排打分）
      - metadata: 元数据（保留传递，不在重排中使用）

    重排前后变化：
      - 输入：candidates 按 粗排 score 降序排列
      - 输出：candidates 按 精排 score 降序排列（score 字段被更新）
      - id/text/metadata 不变，只是顺序和 score 变了
    """
    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# BaseReranker 抽象基类
# ============================================================

class BaseReranker(ABC):
    """Reranker 抽象基类 — 所有重排策略的统一接口

    接口签名：
      rerank(query: str, candidates: list[RerankCandidate]) -> list[RerankCandidate]
      backend_name -> str (property)

    使用方式（上层代码不关心具体重排后端）：
      reranker: BaseReranker = RerankerFactory.create(settings)
      ranked = reranker.rerank("什么是向量数据库？", candidates)

    知识点：为什么用 ABC？
      - ABC + @abstractmethod 强制子类实现 rerank()，忘记实现会 TypeError
      - 面试考点："ABC 的作用？" → 编译期约束 + 类型安全 + 接口契约

    两段式检索架构（面试考点）：
      1. 粗排（Coarse Ranking）：Hybrid Search（BM25+Dense+RRF），快速召回 Top-M 候选
         - 特点：速度快、覆盖率高、精度一般
         - 用 Bi-Encoder（query 和 doc 分离编码，可以预计算）
      2. 精排（Fine Ranking）：Reranker 对 Top-M 候选逐一精排打分，取 Top-K
         - 特点：速度慢、精度高、覆盖率不影响（只重排已有候选）
         - 用 Cross-Encoder（query 和 doc 联合编码，精度高但无法预计算）
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        **kwargs: Any,
    ) -> list[RerankCandidate]:
        """对候选列表进行精排重排序

        接口签名：rerank(query: str, candidates: list[RerankCandidate]) -> list[RerankCandidate]
        入参：
          - query: 用户查询文本
          - candidates: 粗排返回的候选列表（按粗排 score 降序）
        出参：重排后的候选列表（按精排 score 降序）
        异常：RerankerError — 重排失败

        知识点：输入输出同类型
          - 输入 list[RerankCandidate]，输出也是 list[RerankCandidate]
          - 变化的是：顺序（按精排 score 重新排列）和 score（更新为精排分数）
          - 不变的是：每条候选的 id、text、metadata
          - 面试考点："rerank 会改变候选内容吗？" → 不会，只改变顺序和 score

        NoneReranker 的特殊行为：
          - 不做任何重排，直接返回原列表
          - score 保持不变
          - 用于 backend=none 或 Reranker 失败时的 fallback
        """
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """返回当前重排后端名称（用于日志和追踪）

        接口签名：backend_name -> str (property)
        示例：'none', 'cross_encoder', 'llm'
        """
        ...

