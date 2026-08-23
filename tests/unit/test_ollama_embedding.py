"""B7.4: Ollama Embedding 测试

测试结构：
  1. OllamaEmbedding 初始化测试（5 个）
  2. OllamaEmbedding embed() 测试（6 个）
  3. 工厂路由测试（2 个）
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from core.settings import EmbeddingSettings
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from libs.embedding.embedding_factory import EmbeddingFactory
from libs.embedding.ollama_embedding import OllamaEmbedding


def make_ollama_embedding_response(dimensions: int = 768) -> dict[str, Any]:
    """构造 Ollama /api/embeddings 响应格式"""
    return {"embedding": [0.01 * i for i in range(dimensions)]}


def make_mock_transport(status_code: int = 200, json_data: dict | None = None, dimensions: int = 768) -> httpx.MockTransport:
    if json_data is None:
        json_data = make_ollama_embedding_response(dimensions)
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_data)
    return httpx.MockTransport(handler)


def patch_httpx(monkeypatch, transport):
    original_init = httpx.Client.__init__
    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)
    monkeypatch.setattr(httpx.Client, "__init__", patched_init)


class TestOllamaEmbeddingInit:

    def test_is_base_embedding(self):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text"))
        assert isinstance(e, BaseEmbedding)

    def test_model_name(self):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text"))
        assert e.model_name == "nomic-embed-text"

    def test_dimensions_nomic(self):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=0))
        assert e.dimensions == 768

    def test_dimensions_mxbai(self):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="mxbai-embed-large", dimensions=0))
        assert e.dimensions == 1024

    def test_requires_model(self):
        with pytest.raises(EmbeddingError, match="model"):
            OllamaEmbedding(EmbeddingSettings(provider="ollama", model=""))

    def test_default_base_url(self):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text"))
        assert "localhost:11434" in e._base_url


class TestOllamaEmbeddingEmbed:

    def test_embed_single_text(self, monkeypatch):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=0))
        transport = make_mock_transport(200, dimensions=768)
        patch_httpx(monkeypatch, transport)
        result = e.embed(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 768

    def test_embed_multiple_texts(self, monkeypatch):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=0))
        transport = make_mock_transport(200, dimensions=768)
        patch_httpx(monkeypatch, transport)
        result = e.embed(["hello", "world", "test"])
        assert len(result) == 3
        assert all(len(v) == 768 for v in result)

    def test_embed_empty_list(self):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text"))
        assert e.embed([]) == []

    def test_embed_connect_error(self, monkeypatch):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text"))
        def raise_connect(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")
        transport = httpx.MockTransport(raise_connect)
        patch_httpx(monkeypatch, transport)
        with pytest.raises(EmbeddingError, match="连接失败"):
            e.embed(["hello"])

    def test_embed_timeout(self, monkeypatch):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nomic-embed-text"))
        def raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout")
        transport = httpx.MockTransport(raise_timeout)
        patch_httpx(monkeypatch, transport)
        with pytest.raises(EmbeddingError, match="超时"):
            e.embed(["hello"])

    def test_embed_model_not_found(self, monkeypatch):
        e = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="nonexistent"))
        transport = make_mock_transport(404, {"error": "model not found"})
        patch_httpx(monkeypatch, transport)
        with pytest.raises(EmbeddingError, match="未找到"):
            e.embed(["hello"])


class TestOllamaEmbeddingFactory:

    def test_factory_creates_ollama(self):
        settings = EmbeddingSettings(provider="ollama", model="nomic-embed-text")
        e = EmbeddingFactory.create(settings)
        assert isinstance(e, OllamaEmbedding)

    def test_factory_ollama_custom_url(self):
        settings = EmbeddingSettings(
            provider="ollama", model="mxbai-embed-large",
            base_url="http://gpu-server:11434",
        )
        e = EmbeddingFactory.create(settings)
        assert isinstance(e, OllamaEmbedding)
        assert e.model_name == "mxbai-embed-large"

