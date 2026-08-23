"""
DeepSeek LLM 实现 — OpenAI-Compatible API

知识点：
  - DeepSeek API 与 OpenAI 格式完全一致
  - 只需改 base_url 为 https://api.deepseek.com/v1
  - 使用 OpenAILLM 的核心逻辑，仅覆盖 base_url
  - 面试考点："DeepSeek 和 OpenAI 的区别？" → API 格式相同，只改 base_url 和 api_key

接口签名：
  DeepSeekLLM(settings: LLMSettings)
  chat(messages: list[dict], **kwargs) -> str
  model_name -> str (property)
"""

from __future__ import annotations

from core.settings import LLMSettings
from libs.llm.openai_llm import OpenAILLM


class DeepSeekLLM(OpenAILLM):
    """DeepSeek LLM 实现 — 继承 OpenAILLM，仅覆盖 base_url

    知识点：继承复用
      - DeepSeek API 与 OpenAI 格式完全一致
      - 继承 OpenAILLM，只覆盖 DEFAULT_BASE_URL
      - 面试考点："为什么用继承而非复制？" → DRY 原则，避免代码重复

    DeepSeek 模型：
      - deepseek-chat：通用对话模型
      - deepseek-coder：代码生成模型
    """

    # DeepSeek API 端点（与 OpenAI 格式一致）
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, settings: LLMSettings) -> None:
        """初始化 DeepSeek LLM

        接口签名：DeepSeekLLM(settings: LLMSettings)
        入参：
          - settings: LLM 配置（需要 api_key 和 model）
        """
        # 如果 settings.base_url 为空，使用 DeepSeek 默认 URL
        if not settings.base_url:
            settings.base_url = self.DEFAULT_BASE_URL
        super().__init__(settings)

