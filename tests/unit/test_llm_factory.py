"""
LLM 工厂与抽象基类的单元测试

知识点：
  - ABC 实例化测试：验证抽象类不能直接实例化
  - 工厂路由测试：验证 provider → 正确的实现类
  - 异常测试：不支持的 provider 应抛出 LLMError
  - FakeLLM 测试桩：返回固定值，不依赖真实 API
  - register() 扩展测试：验证开放-封闭原则

测试覆盖：
  1. BaseLLM 抽象约束 — 不能直接实例化
  2. FakeLLM 行为 — chat() 返回预设回复、model_name 正确
  3. LLMFactory.create 路由 — provider="fake" → FakeLLM
  4. LLMFactory.create 错误 — 不支持的 provider → LLMError
  5. LLMFactory.register 扩展 — 注册新 Provider 成功
  6. LLMFactory.register 校验 — 非 BaseLLM 子类 → LLMError
  7. 大小写无关 — provider="Fake" / "FAKE" 都能路由
"""

import pytest

from core.settings import LLMSettings
from libs.llm.base_llm import BaseLLM, LLMError, MessageType
from libs.llm.llm_factory import FakeLLM, LLMFactory


# ============================================================
# BaseLLM 抽象约束测试
# ============================================================

class TestBaseLLMAbstract:
    """验证 BaseLLM 的抽象约束"""

    def test_cannot_instantiate_base_llm(self):
        """BaseLLM 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError, match="abstract method"):
            BaseLLM()  # type: ignore

    def test_subclass_must_implement_chat(self):
        """子类必须实现 chat() 方法"""

        class IncompleteLLM(BaseLLM):
            """只实现了 model_name，没实现 chat"""
            @property
            def model_name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteLLM()  # type: ignore

    def test_subclass_must_implement_model_name(self):
        """子类必须实现 model_name 属性"""

        class IncompleteLLM2(BaseLLM):
            """只实现了 chat，没实现 model_name"""
            def chat(self, messages: list[MessageType], **kwargs) -> str:
                return "test"

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteLLM2()  # type: ignore

    def test_complete_subclass_can_instantiate(self):
        """完整实现所有抽象方法的子类可以实例化"""

        class CompleteLLM(BaseLLM):
            def chat(self, messages: list[MessageType], **kwargs) -> str:
                return "complete"
            @property
            def model_name(self) -> str:
                return "complete-model"

        llm = CompleteLLM()
        assert llm.chat([]) == "complete"
        assert llm.model_name == "complete-model"


# ============================================================
# FakeLLM 测试
# ============================================================

class TestFakeLLM:
    """验证 FakeLLM 测试桩的行为"""

    def test_default_response(self):
        """默认返回 'fake response'"""
        settings = LLMSettings(provider="fake", model="fake-model")
        llm = FakeLLM(settings)
        assert llm.chat([{"role": "user", "content": "hello"}]) == "fake response"

    def test_custom_response(self):
        """可以设置自定义回复"""
        settings = LLMSettings(provider="fake", model="fake-model")
        llm = FakeLLM(settings, response="custom answer")
        assert llm.chat([]) == "custom answer"

    def test_model_name_from_settings(self):
        """model_name 来自 settings.model"""
        settings = LLMSettings(provider="fake", model="my-fake-model")
        llm = FakeLLM(settings)
        assert llm.model_name == "my-fake-model"

    def test_model_name_default_when_empty(self):
        """settings.model 为空时使用默认值 'fake-model'"""
        settings = LLMSettings(provider="fake", model="")
        llm = FakeLLM(settings)
        assert llm.model_name == "fake-model"

    def test_is_base_llm_instance(self):
        """FakeLLM 是 BaseLLM 的实例"""
        settings = LLMSettings(provider="fake")
        llm = FakeLLM(settings)
        assert isinstance(llm, BaseLLM)

    def test_chat_ignores_messages(self):
        """FakeLLM 不关心 messages 内容，始终返回预设回复"""
        settings = LLMSettings(provider="fake")
        llm = FakeLLM(settings, response="fixed")

        msg1 = llm.chat([{"role": "user", "content": "问题1"}])
        msg2 = llm.chat([{"role": "user", "content": "完全不同的问题"}])

        assert msg1 == "fixed"
        assert msg2 == "fixed"


# ============================================================
# LLMFactory 路由测试
# ============================================================

class TestLLMFactoryRouting:
    """验证 LLMFactory 的路由逻辑"""

    def test_create_fake_llm(self):
        """provider='fake' → FakeLLM"""
        settings = LLMSettings(provider="fake", model="test-model")
        llm = LLMFactory.create(settings)

        assert isinstance(llm, FakeLLM)
        assert llm.model_name == "test-model"

    def test_create_fake_llm_chat_works(self):
        """通过工厂创建的 FakeLLM 可以正常调用 chat()"""
        settings = LLMSettings(provider="fake", model="test-model")
        llm = LLMFactory.create(settings)
        response = llm.chat([{"role": "user", "content": "hello"}])

        assert isinstance(response, str)
        assert response == "fake response"

    def test_unsupported_provider_raises_error(self):
        """不支持的 provider → LLMError"""
        settings = LLMSettings(provider="nonexistent_provider")
        with pytest.raises(LLMError, match="不支持的 LLM provider"):
            LLMFactory.create(settings)

    def test_unsupported_provider_lists_supported(self):
        """错误信息中列出所有支持的 provider"""
        settings = LLMSettings(provider="invalid")
        with pytest.raises(LLMError, match="fake"):
            LLMFactory.create(settings)

    def test_case_insensitive_provider(self):
        """provider 名称大小写无关"""
        for provider_name in ["fake", "Fake", "FAKE", "FaKe"]:
            settings = LLMSettings(provider=provider_name, model="test")
            llm = LLMFactory.create(settings)
            assert isinstance(llm, FakeLLM)

    def test_provider_with_whitespace(self):
        """provider 名称前后空格不影响路由"""
        settings = LLMSettings(provider="  fake  ", model="test")
        llm = LLMFactory.create(settings)
        assert isinstance(llm, FakeLLM)

    def test_empty_provider_raises_error(self):
        """provider 为空字符串 → LLMError"""
        settings = LLMSettings(provider="")
        with pytest.raises(LLMError, match="不支持的 LLM provider"):
            LLMFactory.create(settings)


# ============================================================
# LLMFactory 注册扩展测试
# ============================================================

class TestLLMFactoryRegister:
    """验证 LLMFactory.register() 的开放-封闭原则"""

    def test_register_custom_provider(self):
        """注册自定义 Provider 后可以通过工厂创建"""

        class CustomLLM(BaseLLM):
            # 知识点：工厂模式要求所有实现类接受 settings 参数
            # LLMFactory.create() 统一调用 llm_class(settings)
            def __init__(self, settings: LLMSettings) -> None:
                self._model = settings.model or "custom-model"

            def chat(self, messages: list[MessageType], **kwargs) -> str:
                return "custom response"
            @property
            def model_name(self) -> str:
                return self._model

        LLMFactory.register("custom", CustomLLM)

        try:
            settings = LLMSettings(provider="custom", model="custom-model")
            llm = LLMFactory.create(settings)

            assert isinstance(llm, CustomLLM)
            assert llm.chat([]) == "custom response"
            assert llm.model_name == "custom-model"
        finally:
            # 清理：移除注册的 Provider，避免影响其他测试
            LLMFactory._PROVIDERS.pop("custom", None)

    def test_register_non_base_llm_raises_error(self):
        """注册非 BaseLLM 子类 → LLMError"""

        class NotAnLLM:
            def chat(self):
                return "oops"

        with pytest.raises(LLMError, match="不是 BaseLLM 的子类"):
            LLMFactory.register("bad", NotAnLLM)  # type: ignore

    def test_register_overwrite_existing(self):
        """注册同名 Provider 会覆盖原有实现"""

        class AnotherFakeLLM(BaseLLM):
            def __init__(self, settings: LLMSettings) -> None:
                self._model = settings.model or "another-fake"

            def chat(self, messages: list[MessageType], **kwargs) -> str:
                return "another fake"
            @property
            def model_name(self) -> str:
                return self._model

        original = LLMFactory._PROVIDERS.get("fake")

        try:
            LLMFactory.register("fake", AnotherFakeLLM)
            settings = LLMSettings(provider="fake")
            llm = LLMFactory.create(settings)

            assert isinstance(llm, AnotherFakeLLM)
            assert llm.chat([]) == "another fake"
        finally:
            # 恢复原始 FakeLLM
            if original is not None:
                LLMFactory._PROVIDERS["fake"] = original
