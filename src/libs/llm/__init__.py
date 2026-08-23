"""
LLM 模块 — 可插拔的 LLM 抽象层

导出：
  - BaseLLM: 抽象基类，所有 LLM 实现的统一接口
  - LLMError: LLM 调用异常
  - LLMFactory: 工厂类，根据配置创建对应实现
  - FakeLLM: 测试桩，不依赖真实 API
  - OpenAILLM: OpenAI API 实现
  - AzureLLM: Azure OpenAI 实现
  - DeepSeekLLM: DeepSeek API 实现（OpenAI-Compatible）
"""

from libs.llm.llm_factory import FakeLLM, LLMFactory

__all__ = [
    "BaseLLM",
    "LLMError",
    "LLMFactory",
    "FakeLLM",
    "MessageType",
]

