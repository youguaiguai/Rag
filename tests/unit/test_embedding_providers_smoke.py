"""B7.3: OpenAI & Azure Embedding Smoke 测试

测试结构：
  1. OpenAIEmbedding 测试（8 个）
  2. AzureEmbedding 测试（7 个）
  3. 工厂路由测试（3 个）

所有测试 mock HTTP，不走真实网络。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from core.settings import EmbeddingSettings
from libs.embedding.azure_embedding import AzureEmbedding
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from libs.embedding.embedding_factory import EmbeddingFactory
from libs.embedding.openai_embedding import OpenAIEmbedding


def make_embedding_response(vectors: list[list[float]] | None = None) -> dict[str, Any]:
    """构造 OpenAI 格式的 Embedding 响应"""
    if vectors is None:
        vectors = [[0.01 * i for i in range(1536)], [0.02 * i for i in range(1536)]]
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": v}
            for i, v in enumerate(vectors)
        ],
    }


def make_mock_transport(status_code: int = 200, json_data: dict | None = None) -> httpx.MockTransport:
    if json_data is None:
        json_data = make_embedding_response()
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_data)
    return httpx.MockTransport(handler)


def patch_httpx(monkeypatch, transport):
    """Patch httpx.Client to use mock transport"""
    original_init = httpx.Client.__init__
    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)
    monkeypatch.setattr(httpx.Client, "__init__", patched_init)


# ============================================================
# 1. OpenAIEmbedding 测试
# ============================================================

class TestOpenAIEmbedding:

    def test_is_base_embedding(self):
        e = OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key="sk-test"))
        assert isinstance(e, BaseEmbedding)

    def test_model_name(self):
        e = OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key="sk-test"))
        assert e.model_name == "text-embedding-3-small"

    def test_dimensions_small(self):
        e = OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key="sk-test"))
        assert e.dimensions == 1536

    def test_dimensions_large(self):
        e = OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-large", api_key="sk-test", dimensions=0))
        assert e.dimensions == 3072

    def test_requires_api_key(self):
        with pytest.raises(EmbeddingError, match="api_key"):
            OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key=""))

    def test_requires_model(self):
        with pytest.raises(EmbeddingError, match="model"):
            OpenAIEmbedding(EmbeddingSettings(provider="openai", model="", api_key="sk-test"))

    def test_embed_success(self, monkeypatch):
        e = OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key="sk-test"))
        vec = [[0.1] * 1536, [0.2] * 1536]
        transport = make_mock_transport(200, make_embedding_response(vec))
        patch_httpx(monkeypatch, transport)
        result = e.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 1536

    def test_embed_empty_list(self):
        e = OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key="sk-test"))
        assert e.embed([]) == []

    def test_embed_http_error(self, monkeypatch):
        e = OpenAIEmbedding(EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key="bad"))
        transport = make_mock_transport(401, {"error": "invalid key"})
        patch_httpx(monkeypatch, transport)
        with pytest.raises(EmbeddingError, match="认证失败"):
            e.embed(["hello"])


# ============================================================
# 2. AzureEmbedding 测试
# ============================================================

class TestAzureEmbedding:

    def test_is_base_embedding(self):
        settings = EmbeddingSettings(
            provider="azure", model="text-embedding-ada-002", api_key="key",
            azure_endpoint="https://x.openai.azure.com", deployment_name="deploy",
        )
        e = AzureEmbedding(settings)
        assert isinstance(e, BaseEmbedding)

    def test_requires_azure_endpoint(self):
        with pytest.raises(EmbeddingError, match="azure_endpoint"):
            AzureEmbedding(EmbeddingSettings(provider="azure", api_key="key", deployment_name="dep"))

    def test_requires_deployment_name(self):
        with pytest.raises(EmbeddingError, match="deployment_name"):
            AzureEmbedding(EmbeddingSettings(
                provider="azure", api_key="key",
                azure_endpoint="https://x.openai.azure.com",
            ))

    def test_model_defaults_to_deployment(self):
        settings = EmbeddingSettings(
            provider="azure", api_key="key",
            azure_endpoint="https://x.openai.azure.com",
            deployment_name="my-deploy",
        )
        e = AzureEmbedding(settings)
        assert e.model_name == "my-deploy"

    def test_dimensions_ada_002(self):
        settings = EmbeddingSettings(
            provider="azure", model="text-embedding-ada-002", api_key="key",
            azure_endpoint="https://x.openai.azure.com", deployment_name="deploy",
        )
        e = AzureEmbedding(settings)
        assert e.dimensions == 1536

    def test_embed_success(self, monkeypatch):
        settings = EmbeddingSettings(
            provider="azure", model="text-embedding-ada-002", api_key="key",
            azure_endpoint="https://x.openai.azure.com", deployment_name="deploy",
        )
        e = AzureEmbedding(settings)
        vec = [[0.3] * 1536]
        transport = make_mock_transport(200, make_embedding_response(vec))
        patch_httpx(monkeypatch, transport)
        result = e.embed(["test"])
        assert len(result) == 1
        assert len(result[0]) == 1536

    def test_embed_http_error(self, monkeypatch):
        settings = EmbeddingSettings(
            provider="azure", api_key="bad",
            azure_endpoint="https://x.openai.azure.com", deployment_name="deploy",
        )
        e = AzureEmbedding(settings)
        transport = make_mock_transport(401, {"error": "invalid"})
        patch_httpx(monkeypatch, transport)
        with pytest.raises(EmbeddingError, match="认证失败"):
            e.embed(["test"])


# ============================================================
# 3. 工厂路由测试
# ============================================================

class TestEmbeddingFactoryRouting:

    def test_factory_creates_openai(self):
        settings = EmbeddingSettings(provider="openai", model="text-embedding-3-small", api_key="sk-test")
        e = EmbeddingFactory.create(settings)
        assert isinstance(e, OpenAIEmbedding)

    def test_factory_creates_azure(self):
        settings = EmbeddingSettings(
            provider="azure", model="text-embedding-ada-002", api_key="key",
            azure_endpoint="https://x.openai.azure.com", deployment_name="deploy",
        )
        e = EmbeddingFactory.create(settings)
        assert isinstance(e, AzureEmbedding)

    def test_factory_creates_fake(self):
        settings = EmbeddingSettings(provider="fake", model="fake-model")
        e = EmbeddingFactory.create(settings)
        assert e.model_name == "fake-model"

