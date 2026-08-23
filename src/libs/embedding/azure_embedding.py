"""
Azure OpenAI Embedding 实现 — 复用 OpenAI Embedding 核心逻辑

知识点：
  - Azure Embedding API 与 OpenAI 类似，但 URL 格式和认证方式不同
  - URL: {azure_endpoint}/openai/deployments/{deployment_name}/embeddings?api-version={api_version}
  - 认证：api-key header（不是 Bearer token）
  - Azure 实现复用 OpenAI Embedding 的核心逻辑，保持行为一致性
  - 面试考点："Azure Embedding 和 OpenAI 的区别？" → URL 格式 + 认证方式

接口签名：
  AzureEmbedding(settings: EmbeddingSettings)
  embed(texts: list[str]) -> list[list[float]]
  model_name -> str (property)
  dimensions -> int (property)
"""

from __future__ import annotations

from typing import Any

import httpx
from core.settings import EmbeddingSettings
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError


class AzureEmbedding(BaseEmbedding):
    """Azure OpenAI Embedding 实现

    知识点：Azure Embedding 特殊性
      - URL 格式与 OpenAI 不同
      - 认证方式：api-key header
      - deployment_name 替代 model（Azure 中按部署管理）
      - 面试考点："Azure 为什么要 deployment？" → Azure 中模型按部署实例管理
    """

    DEFAULT_API_VERSION = "2024-02-15-preview"
    DEFAULT_TIMEOUT = 30.0

    # Azure 部署模型常见维度
    MODEL_DIMENSIONS = {
        "text-embedding-ada-002": 1536,
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }

    def __init__(self, settings: EmbeddingSettings) -> None:
        """初始化 Azure Embedding

        接口签名：AzureEmbedding(settings: EmbeddingSettings)
        入参：
          - settings: Embedding 配置（需要 azure_endpoint, deployment_name, api_key）
        异常：EmbeddingError — 必要配置缺失
        """
        if not settings.api_key:
            raise EmbeddingError("Azure Embedding 初始化失败: api_key 不能为空")
        if not settings.azure_endpoint:
            raise EmbeddingError("Azure Embedding 初始化失败: azure_endpoint 不能为空")
        if not settings.deployment_name:
            raise EmbeddingError("Azure Embedding 初始化失败: deployment_name 不能为空")

        self._model = settings.model or settings.deployment_name
        self._api_key = settings.api_key
        self._azure_endpoint = settings.azure_endpoint.rstrip("/")
        self._deployment_name = settings.deployment_name
        self._api_version = settings.api_version or self.DEFAULT_API_VERSION
        self._timeout = self.DEFAULT_TIMEOUT

        if settings.dimensions > 0:
            self._dimensions = settings.dimensions
        else:
            self._dimensions = self.MODEL_DIMENSIONS.get(settings.model, 1536)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """调用 Azure OpenAI Embedding API

        接口签名：embed(texts: list[str]) -> list[list[float]]
        """
        if not texts:
            return []

        payload: dict[str, Any] = {"input": texts}

        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
        }

        url = (
            f"{self._azure_endpoint}/openai/deployments/{self._deployment_name}"
            f"/embeddings?api-version={self._api_version}"
        )

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise EmbeddingError(f"Azure Embedding API 请求超时 ({self._timeout}s)")
        except httpx.ConnectError as e:
            raise EmbeddingError(f"Azure Embedding API 连接失败: {e}")

        if response.status_code != 200:
            self._raise_http_error(response.status_code, response.text)

        try:
            data = response.json()
            vectors = [item["embedding"] for item in data["data"]]
            return vectors
        except (KeyError, IndexError) as e:
            raise EmbeddingError(f"Azure Embedding API 响应解析失败: {e}")

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model

    @property
    def dimensions(self) -> int:
        """返回向量维度"""
        return self._dimensions

    def _raise_http_error(self, status_code: int, body: str) -> None:
        """根据 HTTP 状态码抛出对应的 EmbeddingError"""
        if status_code == 401:
            raise EmbeddingError(f"Azure Embedding API 认证失败 (401): api_key 无效")
        elif status_code == 429:
            raise EmbeddingError(f"Azure Embedding API 速率限制 (429)")
        elif status_code >= 500:
            raise EmbeddingError(f"Azure Embedding API 服务器错误 ({status_code})")
        else:
            raise EmbeddingError(f"Azure Embedding API 错误 ({status_code}): {body[:200]}")

