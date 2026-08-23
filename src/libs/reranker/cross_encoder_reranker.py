"""
Cross-Encoder Reranker 实现 — 使用 Cross-Encoder 对候选打分重排

知识点：
  - Cross-Encoder vs Bi-Encoder：
    - Bi-Encoder（粗排）：query 和 doc 分离编码，可预计算，快但精度低
    - Cross-Encoder（精排）：query 和 doc 联合编码，精度高但慢
  - 面试考点："CrossEncoder 为什么精度高？" → query 和 doc 交互注意力

  - 本实现设计：
    - 使用可注入的 scorer 函数（testability）
    - 默认 scorer 用确定性哈希模拟（不依赖真实模型）
    - 生产环境可注入 sentence-transformers 的 CrossEncoder
    - 面试考点："为什么用注入而非硬编码？" → 可测试性 + 解耦

  - 失败回退信号：
    - scorer 调用失败时返回原始排序（标记 fallback）
    - 供 Core 层 D6 fallback 使用

接口签名：
  CrossEncoderReranker(settings: RerankSettings, scorer: Callable | None = None)
  rerank(query, candidates) -> list[RerankCandidate]
  backend_name -> str (property)
"""

from __future__ import annotations

from core.settings import RerankSettings
from libs.reranker.base_reranker import BaseReranker, RerankCandidate, RerankerError
from typing import Any, Callable

# 默认 scorer 类型：Callable[[str, str], float]
ScorerType = Callable[[str, str], float]


def default_scorer(query: str, document: str) -> float:
    """默认 scorer — 基于文本相似度的确定性打分

    知识点：默认 scorer 的设计
      - 不依赖真实 Cross-Encoder 模型
      - 用 Jaccard 相似度（词汇重叠率）模拟相关性
      - 确定性：相同输入始终输出相同分数
      - 面试考点："为什么不直接用模型？" → 测试需要确定性 + 不依赖外部依赖

    Jaccard 相似度：
      - 将 query 和 doc 分词
      - 计算 交集/并集 的比例
      - 取值 [0, 1]，越大越相关
    """
    query_words = set(query.lower().split())
    doc_words = set(document.lower().split())

    if not query_words or not doc_words:
        return 0.0

    intersection = query_words & doc_words
    union = query_words | doc_words

    return len(intersection) / len(union) if union else 0.0


class CrossEncoderReranker(BaseReranker):
    """Cross-Encoder Reranker 实现

    知识点：Cross-Encoder Rerank 流程
      1. 对每个候选：调用 scorer(query, doc) 获取相关性分数
      2. 按分数降序排列
      3. 更新 candidate.score 为 Cross-Encoder 分数
      4. scorer 调用失败时返回原始排序（fallback）

    scorer 注入设计（面试考点）：
      - 默认用 default_scorer（Jaccard 相似度）
      - 生产环境注入 sentence-transformers 的 CrossEncoder
      - 测试环境注入 mock scorer 保证 deterministic
      - 面试考点："为什么用依赖注入？" → 解耦 + 可测试
    """

    def __init__(self, settings: RerankSettings, scorer: ScorerType | None = None) -> None:
        """初始化 Cross-Encoder Reranker

        接口签名：CrossEncoderReranker(settings, scorer=None)
        入参：
          - settings: Rerank 配置
          - scorer: 打分函数 (query, document) -> float，默认用 default_scorer
        """
        self._top_m = settings.top_m
        self._scorer = scorer if scorer is not None else default_scorer

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        **kwargs: Any,
    ) -> list[RerankCandidate]:
        """使用 Cross-Encoder 对候选进行精排重排序

        接口签名：rerank(query, candidates) -> list[RerankCandidate]
        入参：
          - query: 用户查询
          - candidates: 粗排返回的候选列表
        出参：重排后的候选列表（按 Cross-Encoder 分数降序）
        异常：RerankerError — 重排失败

        处理流程：
          1. 截取 Top-M 候选
          2. 对每条候选调用 scorer 打分
          3. 按分数降序排列
          4. 更新 score
          5. scorer 失败时返回原始排序（fallback）
        """
        if not candidates:
            return []

        # 截取 Top-M
        top_m = min(self._top_m, len(candidates))
        to_rerank = candidates[:top_m]
        remaining = candidates[top_m:]

        # 对每条候选打分
        scored: list[tuple[float, RerankCandidate]] = []
        for candidate in to_rerank:
            try:
                score = self._scorer(query, candidate.text)
            except Exception:
                # scorer 失败，返回原始排序（fallback）
                return list(candidates)

            candidate.score = score
            scored.append((score, candidate))

        # 按分数降序排列
        scored.sort(key=lambda x: x[0], reverse=True)

        ranked = [c for _, c in scored] + remaining
        return ranked

    @property
    def backend_name(self) -> str:
        """返回后端名称"""
        return "cross_encoder"

