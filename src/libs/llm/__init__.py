"""
LLM 模块 — 可插拔的 LLM 抽象层

导出：
  - BaseLLM: 抽象基类，所有 LLM 实现的统一接口
  - LLMError: LLM 调用异常
  - LLMFactory: 工厂类，根据配置创建对应实现
  - FakeLLM: 测试桩，不依赖外部库
  - MessageType: 消息类型别名

  - BaseVisionLLM: Vision LLM 抽象基类
  - VisionLLMFactory: Vision LLM 工厂
  - FakeVisionLLM: Vision LLM 测试桩
  - AzureVisionLLM: Azure OpenAI Vision 实现
"""

from libs.llm.llm_factory import FakeLLM, LLMFactory
from libs.llm.vision_factory import (
    AzureVisionLLM,
    FakeVisionLLM,
    NoneVisionLLM,
    VisionLLMFactory,
)

__all__ = [
    "BaseLLM",
    "LLMError",
    "LLMFactory",
    "FakeLLM",
    "MessageType",
    "BaseVisionLLM",
    "VisionLLMFactory",
    "FakeVisionLLM",
    "NoneVisionLLM",
    "AzureVisionLLM",
]

