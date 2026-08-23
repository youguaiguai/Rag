"""B7.2: Ollama LLM 测试

测试结构：
  1. OllamaLLM 初始化测试（4 个）
  2. OllamaLLM chat() 测试（6 个）
  3. 工厂路由测试（2 个）

所有测试 mock HTTP，不走真实网络。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from core.settings import LLMSettings
from libs.llm.base_llm import BaseLLM, LLMError
from libs.llm.llm_factory import LLMFactory
from libs.llm.ollama_llm import OllamaLLM


def make_ollama_response(content: str = "Ollama reply") -> dict[str, Any]:
    """构造 Ollama /api/chat 响应格式"""
    return {
        "model": "llama3",
        "message": {"role": "assistant", "content": content},
        "done": True,
    }


def make_mock_transport(status_code: int = 200, json_data: dict | None = None) -> httpx.MockTransport:
    if json_data is None:
        json_data = make_ollama_response()
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_data)
    return httpx.MockTransport(handler)


class TestOllamaLLMInit:
    """测试 OllamaLLM 初始化"""

    def test_ollama_llm_is_base_llm(self):
        """OllamaLLM 是 BaseLLM 的子类"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3"))
        assert isinstance(llm, BaseLLM)

    def test_ollama_llm_model_name(self):
        """model_name 返回配置的模型名"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3"))
        assert llm.model_name == "llama3"

    def test_ollama_llm_requires_model(self):
        """model 为空 → LLMError"""
        with pytest.raises(LLMError, match="model"):
            OllamaLLM(LLMSettings(provider="ollama", model=""))

    def test_ollama_llm_default_base_url(self):
        """不传 base_url 时使用默认 localhost:11434"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3"))
        assert "localhost:11434" in llm._base_url


class TestOllamaLLMChat:
    """测试 OllamaLLM chat() 方法"""

    def test_chat_success(self, monkeypatch):
        """chat() 成功调用"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3"))
        transport = make_mock_transport(200, make_ollama_response("你好！"))
        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)
        monkeypatch.setattr(httpx.Client, "__init__", patched_init)
        result = llm.chat([{"role": "user", "content": "你好"}])
        assert result == "你好！"

    def test_chat_connect_error(self, monkeypatch):
        """连接失败 → LLMError（不泄露敏感配置）"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3"))
        def raise_connect(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")
        transport = httpx.MockTransport(raise_connect)
        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)
        monkeypatch.setattr(httpx.Client, "__init__", patched_init)
        with pytest.raises(LLMError, match="连接失败"):
            llm.chat([{"role": "user", "content": "hi"}])

    def test_chat_timeout(self, monkeypatch):
        """超时 → LLMError"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3"))
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

    def test_chat_model_not_found(self, monkeypatch):
        """HTTP 404 → 模型未找到"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="nonexistent"))
        transport = make_mock_transport(404, {"error": "model not found"})
        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)
        monkeypatch.setattr(httpx.Client, "__init__", patched_init)
        with pytest.raises(LLMError, match="未找到"):
            llm.chat([{"role": "user", "content": "hi"}])

    def test_chat_500_error(self, monkeypatch):
        """HTTP 500 → 服务器错误"""
        llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3"))
        transport = make_mock_transport(500, {"error": "internal"})
        original_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)
        monkeypatch.setattr(httpx.Client, "__init__", patched_init)
        with pytest.raises(LLMError, match="服务器错误"):
            llm.chat([{"role": "user", "content": "hi"}])

    def test_chat_custom_base_url(self, monkeypatch):
        """自定义 base_url 可正常使用"""
        llm = OllamaLLM(LLMSettings(
            provider="ollama", model="llama3",
            base_url="http://192.168.1.100:11434",
        ))
        assert "192.168.1.100" in llm._base_url


class TestOllamaFactoryRouting:
    """测试工厂路由"""

    def test_factory_creates_ollama(self):
        """provider=ollama → OllamaLLM"""
        settings = LLMSettings(provider="ollama", model="llama3")
        llm = LLMFactory.create(settings)
        assert isinstance(llm, OllamaLLM)

    def test_factory_ollama_with_custom_url(self):
        """provider=ollama + 自定义 base_url"""
        settings = LLMSettings(
            provider="ollama", model="qwen2",
            base_url="http://gpu-server:11434",
        )
        llm = LLMFactory.create(settings)
        assert isinstance(llm, OllamaLLM)
        assert llm.model_name == "qwen2"

