"""B8: Vision LLM 单元测试

测试结构：
  1. BaseVisionLLM ABC 契约测试（3 个）
  2. FakeVisionLLM 测试（6 个）
  3. NoneVisionLLM 空对象测试（3 个）
  4. AzureVisionLLM 初始化测试（5 个）
  5. AzureVisionLLM caption_image 测试（6 个 — 使用 httpx MockTransport）
  6. VisionLLMFactory 工厂路由测试（5 个）
"""

from __future__ import annotations

import base64
import httpx
import json
import pytest
from core.settings import VisionLLMSettings
from libs.llm.azure_vision_llm import AzureVisionLLM
from libs.llm.base_llm import LLMError
from libs.llm.base_vision_llm import BaseVisionLLM
from libs.llm.vision_factory import (
    FakeVisionLLM,
    NoneVisionLLM,
    VisionLLMFactory,
)
from typing import Any


# ============================================================
# 1. BaseVisionLLM ABC 契约测试
# ============================================================

class TestBaseVisionLLMContract:
    """测试抽象基类的约束力"""

    def test_cannot_instantiate_abc(self):
        """ABC 不能直接实例化"""
        with pytest.raises(TypeError):
            BaseVisionLLM()

    def test_subclass_without_methods_fails(self):
        """子类未实现抽象方法 → TypeError"""

        class IncompleteVision(BaseVisionLLM):
            pass

        with pytest.raises(TypeError):
            IncompleteVision()

    def test_subclass_with_methods_works(self):
        """子类实现所有抽象方法 → 可实例化"""

        class CompleteVision(BaseVisionLLM):
            def caption_image(self, image_base64: str, prompt: str = "", **kwargs: Any) -> str:
                return "test"
            @property
            def model_name(self) -> str:
                return "test-model"
            @property
            def provider_name(self) -> str:
                return "test"

        v = CompleteVision()
        assert v.caption_image("base64") == "test"
        assert v.model_name == "test-model"
        assert v.provider_name == "test"


# ============================================================
# 2. FakeVisionLLM 测试
# ============================================================

class TestFakeVisionLLM:

    def test_is_base_vision_llm(self):
        v = FakeVisionLLM(VisionLLMSettings(provider="fake"))
        assert isinstance(v, BaseVisionLLM)

    def test_provider_name(self):
        v = FakeVisionLLM(VisionLLMSettings(provider="fake"))
        assert v.provider_name == "fake"

    def test_model_name_default(self):
        v = FakeVisionLLM(VisionLLMSettings(provider="fake"))
        assert v.model_name == "fake-vision-model"

    def test_model_name_custom(self):
        settings = VisionLLMSettings(provider="fake", model="my-vision-model")
        v = FakeVisionLLM(settings)
        assert v.model_name == "my-vision-model"

    def test_caption_returns_default_response(self):
        """默认返回预设描述"""
        v = FakeVisionLLM(VisionLLMSettings(provider="fake"))
        result = v.caption_image("some_base64_data")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_caption_with_custom_response(self):
        """自定义 response 被正确返回"""
        v = FakeVisionLLM(
            VisionLLMSettings(provider="fake"),
            response="这是一张架构图。",
        )
        result = v.caption_image("base64_data")
        assert result == "这是一张架构图。"


# ============================================================
# 3. NoneVisionLLM 空对象测试
# ============================================================

class TestNoneVisionLLM:

    def test_is_base_vision_llm(self):
        v = NoneVisionLLM()
        assert isinstance(v, BaseVisionLLM)

    def test_caption_returns_empty_string(self):
        """空对象返回空字符串"""
        v = NoneVisionLLM()
        result = v.caption_image("some_base64_data")
        assert result == ""

    def test_model_and_provider_name(self):
        v = NoneVisionLLM()
        assert v.model_name == "none"
        assert v.provider_name == "none"


# ============================================================
# 4. AzureVisionLLM 初始化测试
# ============================================================

class TestAzureVisionLLMInit:

    def test_is_base_vision_llm(self):
        settings = VisionLLMSettings(
            enabled=True,
            provider="azure",
            model="gpt-4o",
            api_key="test-key",
            azure_endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4o-deployment",
        )
        v = AzureVisionLLM(settings)
        assert isinstance(v, BaseVisionLLM)

    def test_provider_name(self):
        settings = VisionLLMSettings(
            enabled=True,
            provider="azure",
            api_key="key",
            azure_endpoint="https://test.openai.azure.com",
            deployment_name="deploy",
        )
        v = AzureVisionLLM(settings)
        assert v.provider_name == "azure"

    def test_init_missing_api_key(self):
        """缺少 api_key → LLMError"""
        settings = VisionLLMSettings(
            provider="azure",
            azure_endpoint="https://test.openai.azure.com",
            deployment_name="deploy",
        )
        with pytest.raises(LLMError, match="api_key"):
            AzureVisionLLM(settings)

    def test_init_missing_endpoint(self):
        """缺少 azure_endpoint → LLMError"""
        settings = VisionLLMSettings(
            provider="azure",
            api_key="key",
            deployment_name="deploy",
        )
        with pytest.raises(LLMError, match="azure_endpoint"):
            AzureVisionLLM(settings)

    def test_init_missing_deployment(self):
        """缺少 deployment_name → LLMError"""
        settings = VisionLLMSettings(
            provider="azure",
            api_key="key",
            azure_endpoint="https://test.openai.azure.com",
        )
        with pytest.raises(LLMError, match="deployment_name"):
            AzureVisionLLM(settings)

    def test_model_name_from_deployment(self):
        """model 为空时用 deployment_name"""
        settings = VisionLLMSettings(
            provider="azure",
            api_key="key",
            azure_endpoint="https://test.openai.azure.com",
            deployment_name="my-deployment",
        )
        v = AzureVisionLLM(settings)
        assert v.model_name == "my-deployment"


# ============================================================
# 5. AzureVisionLLM caption_image 测试（使用 httpx MockTransport）
# ============================================================

def make_mock_transport(response_body: dict, status_code: int = 200) -> httpx.MockTransport:
    """创建 MockTransport，返回预设响应

    知识点：httpx.MockTransport
      - 拦截 HTTP 请求，不发送到真实服务器
      - 返回预设的响应
      - 用于测试不依赖外部网络
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=response_body,
        )
    return httpx.MockTransport(handler)


class TestAzureVisionLLMCaption:

    def _make_settings(self, **overrides) -> VisionLLMSettings:
        defaults = dict(
            enabled=True,
            provider="azure",
            model="gpt-4o",
            api_key="test-key",
            azure_endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4o-deploy",
        )
        defaults.update(overrides)
        return VisionLLMSettings(**defaults)

    def test_caption_success(self):
        """正常调用返回描述文本"""
        mock_response = {
            "choices": [
                {"message": {"role": "assistant", "content": "这是一张架构图，展示了系统组件。"}}
            ]
        }
        mock_transport = make_mock_transport(mock_response)

        settings = self._make_settings()
        v = AzureVisionLLM(settings)

        # Monkey-patch httpx.Client to use MockTransport
        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = mock_transport
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        try:
            result = v.caption_image("base64_encoded_image_data", "描述图片")
        finally:
            httpx.Client.__init__ = original_init

        assert result == "这是一张架构图，展示了系统组件。"

    def test_caption_empty_image_raises(self):
        """image_base64 为空 → LLMError"""
        settings = self._make_settings()
        v = AzureVisionLLM(settings)
        with pytest.raises(LLMError, match="image_base64"):
            v.caption_image("")

    def test_caption_uses_default_prompt_when_empty(self):
        """prompt 为空时使用默认描述指令"""
        mock_response = {
            "choices": [
                {"message": {"role": "assistant", "content": "图片描述"}}
            ]
        }
        mock_transport = make_mock_transport(mock_response)
        settings = self._make_settings()
        v = AzureVisionLLM(settings)

        original_init = httpx.Client.__init__
        captured_requests: list[httpx.Request] = []

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = mock_transport
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        try:
            result = v.caption_image("base64_data", "")
        finally:
            httpx.Client.__init__ = original_init

        assert result == "图片描述"

    def test_caption_http_401(self):
        """HTTP 401 → LLMError 认证失败"""
        mock_transport = make_mock_transport({"error": "unauthorized"}, status_code=401)
        settings = self._make_settings()
        v = AzureVisionLLM(settings)

        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = mock_transport
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        try:
            with pytest.raises(LLMError, match="401"):
                v.caption_image("base64_data")
        finally:
            httpx.Client.__init__ = original_init

    def test_caption_http_429(self):
        """HTTP 429 → LLMError 速率限制"""
        mock_transport = make_mock_transport({"error": "rate limited"}, status_code=429)
        settings = self._make_settings()
        v = AzureVisionLLM(settings)

        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = mock_transport
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        try:
            with pytest.raises(LLMError, match="429"):
                v.caption_image("base64_data")
        finally:
            httpx.Client.__init__ = original_init

    def test_caption_http_400(self):
        """HTTP 400 → LLMError 图片格式错误"""
        mock_transport = make_mock_transport({"error": "bad request"}, status_code=400)
        settings = self._make_settings()
        v = AzureVisionLLM(settings)

        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = mock_transport
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        try:
            with pytest.raises(LLMError, match="400"):
                v.caption_image("base64_data")
        finally:
            httpx.Client.__init__ = original_init

    def test_caption_malformed_response_raises(self):
        """响应缺少 choices 字段 → LLMError"""
        mock_transport = make_mock_transport({"unexpected": "response"})
        settings = self._make_settings()
        v = AzureVisionLLM(settings)

        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = mock_transport
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        try:
            with pytest.raises(LLMError, match="解析失败"):
                v.caption_image("base64_data")
        finally:
            httpx.Client.__init__ = original_init


# ============================================================
# 6. VisionLLMFactory 工厂路由测试
# ============================================================

class TestVisionLLMFactory:

    def test_factory_disabled_returns_none_vision(self):
        """enabled=false → NoneVisionLLM"""
        settings = VisionLLMSettings(enabled=False)
        v = VisionLLMFactory.create(settings)
        assert isinstance(v, NoneVisionLLM)
        assert v.provider_name == "none"

    def test_factory_creates_fake(self):
        """provider=fake → FakeVisionLLM"""
        settings = VisionLLMSettings(enabled=True, provider="fake", model="test-model")
        v = VisionLLMFactory.create(settings)
        assert isinstance(v, FakeVisionLLM)
        assert v.provider_name == "fake"

    def test_factory_creates_azure(self):
        """provider=azure → AzureVisionLLM"""
        settings = VisionLLMSettings(
            enabled=True,
            provider="azure",
            model="gpt-4o",
            api_key="key",
            azure_endpoint="https://test.openai.azure.com",
            deployment_name="deploy",
        )
        v = VisionLLMFactory.create(settings)
        assert isinstance(v, AzureVisionLLM)
        assert v.provider_name == "azure"

    def test_factory_unknown_provider_raises(self):
        """未知 provider → LLMError"""
        settings = VisionLLMSettings(enabled=True, provider="unknown_provider")
        with pytest.raises(LLMError, match="不支持"):
            VisionLLMFactory.create(settings)

    def test_factory_register_custom_provider(self):
        """register() 注册自定义 Provider"""

        class CustomVision(BaseVisionLLM):
            def __init__(self, settings: VisionLLMSettings, **kwargs: Any) -> None:
                pass
            def caption_image(self, image_base64: str, prompt: str = "", **kwargs: Any) -> str:
                return "custom"
            @property
            def model_name(self) -> str:
                return "custom-model"
            @property
            def provider_name(self) -> str:
                return "custom"

        VisionLLMFactory.register("custom", CustomVision)
        settings = VisionLLMSettings(enabled=True, provider="custom")
        v = VisionLLMFactory.create(settings)
        assert isinstance(v, CustomVision)
        assert v.provider_name == "custom"

