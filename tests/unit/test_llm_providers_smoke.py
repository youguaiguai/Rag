"""B7.1: OpenAI-Compatible LLM Smoke 测试

测试结构：
  1. OpenAILLM 测试（8 个）
  2. AzureLLM 测试（7 个）
  3. DeepSeekLLM 测试（5 个）
  4. 工厂路由测试（5 个）

所有测试 mock HTTP，不走真实网络。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from core.settings import LLMSettings
from libs.llm.azure_llm import AzureLLM
from libs.llm.base_llm import BaseLLM, LLMError
from libs.llm.deepseek_llm import DeepSeekLLM
from libs.llm.llm_factory import LLMFactory
from libs.llm.openai_llm import OpenAILLM


# ============================================================
# Mock HTTP 响应工具
# ============================================================

def make_chat_response(content: str = "Hello!") -> dict[str, Any]:
    """构造 OpenAI 格式的 Chat Completion 响应"""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def make_mock_transport(status_code: int = 200, json_data: dict | None = None) -> httpx.MockTransport:
    """创建 httpx MockTransport，拦截 HTTP 请求

    知识点：httpx.MockTransport
      - 拦截 httpx.Client 发出的所有 HTTP 请求
      - 不走真实网络，返回预设响应
      - 用于测试 HTTP 客户端代码
    """
    if json_data is None:
        json_data = make_chat_response()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_data)

    return httpx.MockTransport(handler)


# ============================================================
# 1. OpenAILLM 测试
# ============================================================

class TestOpenAILLM:
    """测试 OpenAI LLM 实现"""

    def test_openai_llm_is_base_llm(self):
        """OpenAILLM 是 BaseLLM 的子类"""
        llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-4o", api_key="sk-test"))
        assert isinstance(llm, BaseLLM)

    def test_openai_llm_model_name(self):
        """model_name 返回配置的模型名"""
        llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-4o", api_key="sk-test"))
        assert llm.model_name == "gpt-4o"

    def test_openai_llm_requires_api_key(self):
        """api_key 为空 → LLMError"""
        with pytest.raises(LLMError, match="api_key"):
            OpenAILLM(LLMSettings(provider="openai", model="gpt-4o", api_key=""))

    def test_openai_llm_requires_model(self):
        """model 为空 → LLMError"""
        with pytest.raises(LLMError, match="model"):
            OpenAILLM(LLMSettings(provider="openai", model="", api_key="sk-test"))

    def test_openai_llm_chat_success(self, monkeypatch):
        """chat() 成功调用 → 返回 content"""
        llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-4o", api_key="sk-test"))

        # Mock httpx.Client 的 transport
        transport = make_mock_transport(200, make_chat_response("你好！"))
        original_init = httpx.Client.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        result = llm.chat([{"role": "user", "content": "你好"}])
        assert result == "你好！"

    def test_openai_llm_chat_http_error(self, monkeypatch):
        """chat() HTTP 401 → LLMError"""
        llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-4o", api_key="bad-key"))

        transport = make_mock_transport(401, {"error": {"message": "Invalid API key"}})
        original_init = httpx.Client.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        with pytest.raises(LLMError, match="认证失败"):
            llm.chat([{"role": "user", "content": "hi"}])

    def test_openai_llm_chat_rate_limit(self, monkeypatch):
        """chat() HTTP 429 → LLMError (速率限制)"""
        llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-4o", api_key="sk-test"))

        transport = make_mock_transport(429, {"error": {"message": "Rate limit"}})
        original_init = httpx.Client.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        with pytest.raises(LLMError, match="速率限制"):
            llm.chat([{"role": "user", "content": "hi"}])

    def test_openai_llm_chat_timeout(self, monkeypatch):
        """chat() 超时 → LLMError"""
        llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-4o", api_key="sk-test"))

        def raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout")

        transport = httpx.MockTransport(raise_timeout)
        original_init = httpx.Client.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        with pytest.raises(LLMError, match="超时"):
            llm.chat([{"role": "user", "content": "hi"}])


# ============================================================
# 2. AzureLLM 测试
# ============================================================

class TestAzureLLM:
    """测试 Azure OpenAI LLM 实现"""

    def test_azure_llm_is_base_llm(self):
        """AzureLLM 是 BaseLLM 的子类"""
        settings = LLMSettings(
            provider="azure", model="gpt-4o", api_key="key",
            azure_endpoint="https://myresource.openai.azure.com",
            deployment_name="my-deployment",
        )
        llm = AzureLLM(settings)
        assert isinstance(llm, BaseLLM)

    def test_azure_llm_requires_azure_endpoint(self):
        """azure_endpoint 为空 → LLMError"""
        with pytest.raises(LLMError, match="azure_endpoint"):
            AzureLLM(LLMSettings(provider="azure", api_key="key", deployment_name="dep"))

    def test_azure_llm_requires_deployment_name(self):
        """deployment_name 为空 → LLMError"""
        with pytest.raises(LLMError, match="deployment_name"):
            AzureLLM(LLMSettings(
                provider="azure", api_key="key",
                azure_endpoint="https://x.openai.azure.com",
            ))

    def test_azure_llm_requires_api_key(self):
        """api_key 为空 → LLMError"""
        with pytest.raises(LLMError, match="api_key"):
            AzureLLM(LLMSettings(
                provider="azure", azure_endpoint="https://x.openai.azure.com",
                deployment_name="dep",
            ))

    def test_azure_llm_model_name_defaults_to_deployment(self):
        """model 为空时 model_name 默认为 deployment_name"""
        settings = LLMSettings(
            provider="azure", api_key="key",
            azure_endpoint="https://x.openai.azure.com",
            deployment_name="my-deploy",
        )
        llm = AzureLLM(settings)
        assert llm.model_name == "my-deploy"

    def test_azure_llm_chat_success(self, monkeypatch):
        """chat() 成功调用"""
        settings = LLMSettings(
            provider="azure", model="gpt-4o", api_key="key",
            azure_endpoint="https://myresource.openai.azure.com",
            deployment_name="my-deployment",
        )
        llm = AzureLLM(settings)

        transport = make_mock_transport(200, make_chat_response("Azure reply"))
        original_init = httpx.Client.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        result = llm.chat([{"role": "user", "content": "hi"}])
        assert result == "Azure reply"

    def test_azure_llm_chat_http_error(self, monkeypatch):
        """chat() HTTP 500 → LLMError"""
        settings = LLMSettings(
            provider="azure", api_key="key",
            azure_endpoint="https://x.openai.azure.com",
            deployment_name="dep",
        )
        llm = AzureLLM(settings)

        transport = make_mock_transport(500, {"error": "server error"})
        original_init = httpx.Client.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        with pytest.raises(LLMError, match="服务器错误"):
            llm.chat([{"role": "user", "content": "hi"}])


# ============================================================
# 3. DeepSeekLLM 测试
# ============================================================

class TestDeepSeekLLM:
    """测试 DeepSeek LLM 实现"""

    def test_deepseek_llm_is_openai_llm(self):
        """DeepSeekLLM 继承自 OpenAILLM"""
        llm = DeepSeekLLM(LLMSettings(provider="deepseek", model="deepseek-chat", api_key="sk-ds"))
        assert isinstance(llm, OpenAILLM)
        assert isinstance(llm, BaseLLM)

    def test_deepseek_llm_uses_default_base_url(self):
        """不传 base_url 时使用 DeepSeek 默认 URL"""
        llm = DeepSeekLLM(LLMSettings(provider="deepseek", model="deepseek-chat", api_key="sk-ds"))
        assert "deepseek.com" in llm._base_url

    def test_deepseek_llm_model_name(self):
        """model_name 返回配置的模型名"""
        llm = DeepSeekLLM(LLMSettings(provider="deepseek", model="deepseek-coder", api_key="sk-ds"))
        assert llm.model_name == "deepseek-coder"

    def test_deepseek_llm_chat_success(self, monkeypatch):
        """chat() 成功调用"""
        llm = DeepSeekLLM(LLMSettings(provider="deepseek", model="deepseek-chat", api_key="sk-ds"))

        transport = make_mock_transport(200, make_chat_response("DeepSeek reply"))
        original_init = httpx.Client.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        result = llm.chat([{"role": "user", "content": "hi"}])
        assert result == "DeepSeek reply"

    def test_deepseek_llm_requires_api_key(self):
        """api_key 为空 → LLMError"""
        with pytest.raises(LLMError, match="api_key"):
            DeepSeekLLM(LLMSettings(provider="deepseek", model="deepseek-chat", api_key=""))


# ============================================================
# 4. 工厂路由测试
# ============================================================

class TestLLMFactoryRouting:
    """测试 LLMFactory 能正确路由到各 Provider"""

    def test_factory_creates_openai(self):
        """provider=openai → OpenAILLM"""
        settings = LLMSettings(provider="openai", model="gpt-4o", api_key="sk-test")
        llm = LLMFactory.create(settings)
        assert isinstance(llm, OpenAILLM)

    def test_factory_creates_azure(self):
        """provider=azure → AzureLLM"""
        settings = LLMSettings(
            provider="azure", model="gpt-4o", api_key="key",
            azure_endpoint="https://x.openai.azure.com",
            deployment_name="dep",
        )
        llm = LLMFactory.create(settings)
        assert isinstance(llm, AzureLLM)

    def test_factory_creates_deepseek(self):
        """provider=deepseek → DeepSeekLLM"""
        settings = LLMSettings(provider="deepseek", model="deepseek-chat", api_key="sk-ds")
        llm = LLMFactory.create(settings)
        assert isinstance(llm, DeepSeekLLM)

    def test_factory_creates_fake(self):
        """provider=fake → FakeLLM"""
        settings = LLMSettings(provider="fake", model="fake-model")
        llm = LLMFactory.create(settings)
        assert llm.model_name == "fake-model"

    def test_factory_unknown_provider_raises(self):
        """未知 provider → LLMError"""
        settings = LLMSettings(provider="unknown", model="x")
        with pytest.raises(LLMError, match="不支持"):
            LLMFactory.create(settings)

