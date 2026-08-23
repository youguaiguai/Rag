"""
LLM Reranker 实现 — 使用 LLM 对候选进行相关性打分重排

知识点：
  - LLM Rerank 的原理：让 LLM 判断 query 和 doc 的相关程度
  - 输出 1-10 的相关性评分，按评分重新排列候选
  - 比 CrossEncoder 更灵活（能理解复杂语义）但更慢
  - 面试考点："LLM Rerank vs CrossEncoder？" → LLM 更灵活但慢

  - 失败回退信号：
    - LLM 调用失败时返回原始排序（标记 fallback）
    - 供 Core 层 D6 fallback 使用
    - 面试考点："Reranker 失败怎么办？" → 返回原排序，不阻断流程

接口签名：
  LLMReranker(settings: RerankSettings, llm: BaseLLM)
  rerank(query, candidates) -> list[RerankCandidate]
  backend_name -> str (property)
"""

from __future__ import annotations

import re
from core.settings import RerankSettings
from libs.llm.base_llm import BaseLLM, LLMError
from libs.reranker.base_reranker import BaseReranker, RerankCandidate, RerankerError
from pathlib import Path
from typing import Any


class LLMReranker(BaseReranker):
    """LLM Reranker 实现 — 使用 LLM 对候选进行精排

    知识点：LLM Rerank 流程
      1. 读取 rerank prompt 模板（config/prompts/rerank.txt）
      2. 对每个候选：构造 prompt（query + doc）→ 调用 LLM → 解析评分
      3. 按评分降序排列
      4. 更新 candidate.score 为 LLM 评分
      5. 异常时返回原始排序（fallback）

    评分解析：
      - LLM 输出应为纯数字（1-10）
      - 用正则提取数字，容错非标准输出
      - 解析失败时给默认分 0.0
    """

    DEFAULT_PROMPT_PATH = "config/prompts/rerank.txt"

    def __init__(self, settings: RerankSettings, llm: BaseLLM, prompt_text: str | None = None) -> None:
        """初始化 LLM Reranker

        接口签名：LLMReranker(settings, llm, prompt_text=None)
        入参：
          - settings: Rerank 配置
          - llm: BaseLLM 实例（用于打分调用）
          - prompt_text: 可选，注入 prompt 文本（测试用）
        异常：RerankerError — prompt 加载失败
        """
        self._llm = llm
        self._top_m = settings.top_m

        # 加载 prompt 模板
        if prompt_text:
            self._prompt_template = prompt_text
        else:
            self._prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """从 config/prompts/rerank.txt 加载 prompt 模板

        知识点：prompt 外部化管理
          - prompt 不硬编码在代码中，而是放在配置文件
          - 方便迭代调优，不需要改代码
          - 面试考点："为什么 prompt 放配置文件？" → 可迭代 + 可版本控制
        """
        prompt_path = Path(self.DEFAULT_PROMPT_PATH)
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        # 默认 prompt
        return "请评估以下查询与文档片段的相关程度。\n\n查询：{query}\n文档片段：{document}\n\n请从1到10评分：\n- 1-3：几乎无关\n- 4-6：部分相关\n- 7-9：高度相关\n- 10：完全匹配\n\n只输出数字评分，不要解释。"

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        **kwargs: Any,
    ) -> list[RerankCandidate]:
        """使用 LLM 对候选进行精排重排序

        接口签名：rerank(query, candidates) -> list[RerankCandidate]
        入参：
          - query: 用户查询
          - candidates: 粗排返回的候选列表
        出参：重排后的候选列表（按 LLM 评分降序）
        异常：RerankerError — 重排失败

        处理流程：
          1. 截取 Top-M 候选（只重排前 M 条）
          2. 对每条候选构造 prompt → 调用 LLM → 解析评分
          3. 按评分降序排列
          4. LLM 调用失败时返回原始排序（fallback）
        """
        if not candidates:
            return []

        # 截取 Top-M
        top_m = min(self._top_m, len(candidates))
        to_rerank = candidates[:top_m]
        remaining = candidates[top_m:]

        # 对每条候选用 LLM 打分
        scored: list[tuple[float, RerankCandidate]] = []
        for candidate in to_rerank:
            score = self._score_candidate(query, candidate.text)
            # 更新 candidate 的 score
            candidate.score = score
            scored.append((score, candidate))

        # 按分数降序排列
        scored.sort(key=lambda x: x[0], reverse=True)

        # 重排后的列表 + 未参与重排的剩余候选
        ranked = [c for _, c in scored] + remaining
        return ranked

    def _score_candidate(self, query: str, document: str) -> float:
        """用 LLM 对单个候选打分

        知识点：LLM 评分解析
          - LLM 输出应为纯数字（1-10）
          - 用正则提取数字，容错非标准输出
          - 解析失败给默认分 0.0
          - 归一化到 [0, 1] 范围（score / 10.0）
        """
        prompt = self._prompt_template.format(query=query, document=document)

        try:
            response = self._llm.chat([
                {"role": "user", "content": prompt},
            ])
        except LLMError:
            # LLM 调用失败，返回默认分 0.0（不阻断流程）
            return 0.0

        # 解析评分（容错处理）
        score = self._parse_score(response)
        return score

    def _parse_score(self, response: str) -> float:
        """从 LLM 响应中解析评分

        知识点：LLM 输出解析的容错策略
          - 理想输出：纯数字 "8"
          - 实际可能： "评分：8" / "8分" / "8.5"
          - 用正则提取第一个数字（含小数）
          - 归一化到 [0, 1]
          - 面试考点："LLM 输出不规范怎么办？" → 正则提取 + 默认值
        """
        # 尝试匹配数字（含小数）
        match = re.search(r"(\d+(?:\.\d+)?)", response)
        if match:
            raw_score = float(match.group(1))
            # 归一化到 [0, 1]（假设 1-10 分制）
            return min(raw_score / 10.0, 1.0)
        return 0.0

    @property
    def backend_name(self) -> str:
        """返回后端名称"""
        return "llm"

