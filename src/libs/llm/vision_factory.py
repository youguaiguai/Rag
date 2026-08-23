"""
Vision LLM 工厂 — 根据配置创建对应的 Vision LLM 实例

知识点：
  - 工厂模式 (Factory Pattern)：与 LLMFactory 同构
  - 配置驱动：settings.vision_llm.provider 决定创建哪个 Vision LLM
  - 降级策略：enabled=false 时返回 NoneVisionLLM（空对象模式）
  - 面试考点："Vision LLM 不启用怎么办？" → 返回空对象，不返回 None

工厂路由逻辑：
  provider="azure" → AzureVisionLLM（需 Azure 配置）
  provider="fake"  → FakeVisionLLM（测试桩）

接口签名：
  VisionLLMFactory.create(settings: VisionLLMSettings) -> BaseVisionLLM
"""

from __future__ import annotations

from core.settings import VisionLLMSettings
from libs.llm.azure_vision_llm import AzureVisionLLM
from libs.llm.base_llm import LLMError
from libs.llm.base_vision_llm import BaseVisionLLM
from pathlib import Path
from typing import Any


# ============================================================
# FakeVisionLLM — 测试桩
# ============================================================

class FakeVisionLLM(BaseVisionLLM):
    """Fake Vision LLM 实现 — 测试专用，不调用真实 API

    知识点：测试桩 (Test Stub)
      - 与 FakeLLM 同构设计
      - 返回固定/可预测的图片描述
      - 不依赖真实 Vision API
      - 面试考点："为什么需要 FakeVisionLLM？" → 隔离测试 + 不花钱

    使用场景：
      - 工厂路由测试
      - 集成测试中替代真实 Vision API
      - 开发阶段无 Azure 配置时验证流程
    """

    DEFAULT_RESPONSE = "这是一张测试图片的描述。"
    DEFAULT_PROMPT_PATH = "config/prompts/image_captioning.txt"

    def __init__(
        self,
        settings: VisionLLMSettings,
        response: str = "",
    ) -> None:
        """初始化 FakeVisionLLM

        接口签名：FakeVisionLLM(settings, response="")
        入参：
          - settings: Vision LLM 配置
          - response: 预设的图片描述（默认使用 DEFAULT_RESPONSE）
        """
        self._model = settings.model or "fake-vision-model"
        self._provider = "fake"
        self._response = response or self.DEFAULT_RESPONSE

    def caption_image(self, image_base64: str, prompt: str = "", **kwargs: Any) -> str:
        """返回预设的图片描述

        接口签名：caption_image(image_base64: str, prompt: str) -> str
        出参：预设的图片描述文本

        知识点：FakeVisionLLM 的行为设计
          - 不验证 image_base64 是否有效
          - 直接返回预设字符串
          - 可扩展：根据 image_base64 长度返回不同描述
        """
        return self._response

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model

    @property
    def provider_name(self) -> str:
        """返回 provider 名称"""
        return self._provider


# ============================================================
# NoneVisionLLM — 空对象模式（enabled=false 时使用）
# ============================================================

class NoneVisionLLM(BaseVisionLLM):
    """None Vision LLM — 空对象模式，图片描述功能禁用

    知识点：空对象模式 (Null Object Pattern)
      - 与 NoneReranker 同构设计
      - enabled=false 时不报错，返回空描述
      - 调用方不需要判空（NoneVisionLLM 实现了完整接口）
      - 面试考点："为什么用空对象而非 None？" → 避免 None 检查 + 统一接口

    行为：
      - caption_image() → 返回空字符串 ""
      - 调用方根据空字符串判断是否跳过图片处理
    """

    def caption_image(self, image_base64: str, prompt: str = "", **kwargs: Any) -> str:
        """返回空字符串（表示图片描述功能禁用）

        接口签名：caption_image(image_base64: str, prompt: str) -> str
        出参：空字符串 ""
        """
        return ""

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return "none"

    @property
    def provider_name(self) -> str:
        """返回 provider 名称"""
        return "none"


# ============================================================
# Vision LLM 工厂
# ============================================================

class VisionLLMFactory:
    """Vision LLM 工厂 — 根据 settings.vision_llm.provider 创建对应实例

    接口签名：
      VisionLLMFactory.create(settings: VisionLLMSettings) -> BaseVisionLLM

    知识点：工厂模式三要素
      1. 映射表 _PROVIDERS：provider → 实现类
      2. create() 方法：查映射表 + 创建实例
      3. register() 方法：运行时注册新 Provider

    降级策略：
      - enabled=false → NoneVisionLLM（空对象，不报错）
      - 面试考点："Vision 不启用时工厂返回什么？" → NoneVisionLLM（不是 None）
    """

    _PROVIDERS: dict[str, type[BaseVisionLLM]] = {
        "fake": FakeVisionLLM,
        "azure": AzureVisionLLM,
    }

    @classmethod
    def create(cls, settings: VisionLLMSettings) -> BaseVisionLLM:
        """根据配置创建 Vision LLM 实例

        接口签名：VisionLLMFactory.create(settings: VisionLLMSettings) -> BaseVisionLLM
        入参：Vision LLM 配置对象
        出参：BaseVisionLLM 子类实例
        异常：LLMError — provider 不支持

        处理流程：
          1. enabled=false → 返回 NoneVisionLLM（降级）
          2. 从 settings.provider 获取 provider 名称
          3. 在 _PROVIDERS 映射表中查找
          4. 创建实例并传入 settings
          5. 未找到则抛出 LLMError
        """
        # 未启用时返回 NoneVisionLLM（降级，不报错）
        if not settings.enabled:
            return NoneVisionLLM()

        provider = settings.provider.lower().strip()

        if provider not in cls._PROVIDERS:
            supported = ", ".join(sorted(cls._PROVIDERS.keys()))
            raise LLMError(
                f"不支持的 Vision LLM provider: '{provider}'。"
                f"当前支持: [{supported}]"
            )

        vision_class = cls._PROVIDERS[provider]
        return vision_class(settings)

    @classmethod
    def register(cls, provider: str, vision_class: type[BaseVisionLLM]) -> None:
        """注册新的 Vision LLM Provider

        接口签名：VisionLLMFactory.register(provider: str, vision_class: type) -> None

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增 Provider 不改工厂代码
          - 对修改封闭：create() 方法不需要修改
        """
        if not issubclass(vision_class, BaseVisionLLM):
            raise LLMError(f"注册失败: {vision_class} 不是 BaseVisionLLM 的子类")
        cls._PROVIDERS[provider.lower().strip()] = vision_class

