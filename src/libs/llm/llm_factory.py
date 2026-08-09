"""
LLM 工厂 — 根据配置创建对应的 LLM 实例

知识点：
  - 工厂模式 (Factory Pattern)：将"创建哪个实现"的决策从业务代码中解耦
  - 核心方法：LLMFactory.create(settings) -> BaseLLM
  - 配置驱动：settings.llm.provider 决定创建哪个 LLM 实例
  - 好处：切换 Provider 只改配置，不改代码

工厂路由逻辑：
  provider="openai"   → OpenAILLM（需安装 openai 包）
  provider="azure"    → AzureLLM（需安装 openai 包 + azure 配置）
  provider="ollama"   → OllamaLLM（需 ollama 服务运行）
  provider="deepseek" → DeepSeekLLM（需安装 openai 包 + deepseek api_key）
  provider="fake"     → FakeLLM（测试桩，不调用真实 API）

当前阶段（B1）：
  - 只实现 FakeLLM（测试桩），验证工厂路由逻辑
  - OpenAI/Azure/Ollama/DeepSeek 实现在后续阶段（C1）添加
  - 面试考点："为什么先用 Fake 实现？" → 隔离测试 + 不依赖外部服务

接口签名：
  LLMFactory.create(settings: LLMSettings) -> BaseLLM
    入参：LLM 配置对象
    出参：BaseLLM 子类实例
    异常：LLMError — provider 不支持 / 依赖缺失
"""

from __future__ import annotations

from typing import Any

from core.settings import LLMSettings
from libs.llm.base_llm import BaseLLM, LLMError, MessageType


# ============================================================
# FakeLLM — 测试桩
# ============================================================

class FakeLLM(BaseLLM):
    """Fake LLM 实现 — 测试专用，不调用真实 API

    知识点：测试桩 (Test Stub / Test Double)
      - 目的：隔离测试，不依赖真实 API（省流量 + 省钱 + 稳定）
      - 行为：返回固定的预设回复，或根据输入生成可预测的回复
      - 面试考点："什么是测试桩？" → 替代真实依赖的可控实现

    使用场景：
      - 工厂路由测试：验证 LLMFactory.create() 能正确创建 FakeLLM
      - 集成测试：在完整 Pipeline 中使用 FakeLLM 替代真实 API
      - 回归测试：FakeLLM 返回固定内容，确保测试可重复
    """

    def __init__(self, settings: LLMSettings, response: str = "fake response") -> None:
        """初始化 FakeLLM

        接口签名：FakeLLM(settings: LLMSettings, response: str = "fake response")
        入参：
          - settings: LLM 配置（保存 model_name 等信息）
          - response: 预设的回复内容（默认 "fake response"）
        """
        self._model_name = settings.model or "fake-model"
        self._response = response

    def chat(self, messages: list[MessageType], **kwargs: Any) -> str:
        """返回预设回复

        知识点：FakeLLM.chat() 的行为设计
          - 不做任何计算，直接返回预设字符串
          - 可扩展：根据 messages 内容返回不同的预设回复
          - 面试考点："FakeLLM 和 MockLLM 的区别？"
            → Fake 返回固定值；Mock 记录调用并验证
        """
        return self._response

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model_name


# ============================================================
# LLM 工厂
# ============================================================

class LLMFactory:
    """LLM 工厂 — 根据 settings.llm.provider 创建对应的 LLM 实例

    接口签名：
      LLMFactory.create(settings: LLMSettings) -> BaseLLM

    知识点：工厂模式的三种实现方式
      1. 简单工厂（本项目采用）：一个 create 方法 + if/elif 分支
      2. 工厂方法：每个产品一个工厂类（过度设计）
      3. 抽象工厂：一组相关产品的工厂（本项目不需要）

    为什么选简单工厂？
      - LLM Provider 数量有限（4-5 个），if/elif 够用
      - 代码直观，新人一眼看懂
      - 面试考点："简单工厂 vs 工厂方法？" → 产品少用简单工厂，多用工厂方法
    """

    # Provider → 创建函数的映射表
    # 知识点：用映射表代替 if/elif，更易扩展
    #   新增 Provider 只需加一行映射，不用改 create() 方法
    _PROVIDERS: dict[str, type[BaseLLM]] = {
        "fake": FakeLLM,
    }

    @classmethod
    def create(cls, settings: LLMSettings) -> BaseLLM:
        """根据配置创建 LLM 实例

        接口签名：LLMFactory.create(settings: LLMSettings) -> BaseLLM
        入参：LLM 配置对象（包含 provider、model、api_key 等）
        出参：BaseLLM 子类实例
        异常：LLMError — provider 不支持

        处理流程：
          1. 从 settings.llm.provider 获取 provider 名称
          2. 在 _PROVIDERS 映射表中查找对应的实现类
          3. 创建实例并传入 settings
          4. 未找到则抛出 LLMError

        面试考点：
          "工厂模式的好处？" → 改配置不改代码 + 上层只依赖接口
          "新增 Provider 需要改什么？" → 实现 BaseLLM + 在 _PROVIDERS 注册
        """
        provider = settings.provider.lower().strip()

        if provider not in cls._PROVIDERS:
            supported = ", ".join(sorted(cls._PROVIDERS.keys()))
            raise LLMError(
                f"不支持的 LLM provider: '{provider}'。"
                f"当前支持: [{supported}]"
            )

        llm_class = cls._PROVIDERS[provider]
        return llm_class(settings)

    @classmethod
    def register(cls, provider: str, llm_class: type[BaseLLM]) -> None:
        """注册新的 LLM Provider

        接口签名：LLMFactory.register(provider: str, llm_class: type[BaseLLM]) -> None
        入参：
          - provider: Provider 名称（如 "openai"）
          - llm_class: BaseLLM 子类

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增 Provider 不改工厂代码
          - 对修改封闭：create() 方法不需要修改
          - register() 让第三方代码可以注册自己的 Provider
        """
        if not issubclass(llm_class, BaseLLM):
            raise LLMError(f"注册失败: {llm_class} 不是 BaseLLM 的子类")
        cls._PROVIDERS[provider.lower().strip()] = llm_class
