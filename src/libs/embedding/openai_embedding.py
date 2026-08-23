"""
OpenAI Embedding 实现 — 通过 httpx 调用 OpenAI Embedding API

知识点：
  - OpenAI Embedding API：POST /v1/embeddings
  - 请求格式：{"model": "text-embedding-3-small", "input": ["text1", "text2"]}
  - 响应格式：{"data": [{"embedding": [0.01, ...]}, {"embedding": [0.02, ...]}]}
  - 批量 embed：一次请求处理多条文本，减少 API 调用
  - 面试考点："text-embedding-3-small 维度？" → 1536

接口签名：
  OpenAIEmbedding(settings: EmbeddingSettings)
  embed(texts: list[str]) -> list[list[float]]
  model_name -> str (property)
  dimensions -> int (property)
"""

from __future__ import annotations

from typing import Any

import httpx
from core.settings import EmbeddingSettings
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError


class OpenAIEmbedding(BaseEmbedding):
    """OpenAI Embedding 实现 — 通过 httpx 调用 OpenAI Embedding API

    知识点：Embedding API 与 Chat API 的区别
      - Chat API：输入 messages，输出文本
      - Embedding API：输入文本列表，输出向量列表
      - 两者使用不同的 API 端点
      - 面试考点："Embedding 和 Chat 的区别？" → Embedding 输出向量，Chat 输出文本

    OpenAI Embedding 模型：
      - text-embedding-3-small：1536 维，便宜
      - text-embedding-3-large：3072 维，精度高
      - text-embedding-ada-002：1536 维（旧版）
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    EMBEDDINGS_ENDPOINT = "/embeddings"
    DEFAULT_TIMEOUT = 30.0

    # 常见模型的维度映射
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, settings: EmbeddingSettings) -> None:
        """初始化 OpenAI Embedding

        接口签名：OpenAIEmbedding(settings: EmbeddingSettings)
        入参：
          - settings: Embedding 配置（需要 api_key, model）
        异常：EmbeddingError — api_key 或 model 为空
        """
        if not settings.api_key:
            raise EmbeddingError("OpenAI Embedding 初始化失败: api_key 不能为空")
        if not settings.model:
            raise EmbeddingError("OpenAI Embedding 初始化失败: model 不能为空")

        self._model = settings.model
        self._api_key = settings.api_key
        self._base_url = settings.base_url or self.DEFAULT_BASE_URL
        self._timeout = self.DEFAULT_TIMEOUT

        # 维度：优先用 settings.dimensions，其次用模型默认映射
        if settings.dimensions > 0:
            self._dimensions = settings.dimensions
        else:
            self._dimensions = self.MODEL_DIMENSIONS.get(settings.model, 1536)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """调用 OpenAI Embedding API 批量向量化

        接口签名：embed(texts: list[str]) -> list[list[float]]
        入参：
          - texts: 文本列表
        出参：向量列表，每个向量是 list[float]
        异常：EmbeddingError — API 调用失败 / 空输入

        处理流程：
          1. 校验输入（空列表 → 返回空列表）
          2. 构造请求体
          3. 发送 HTTP POST
          4. 解析响应，提取 embeddings
          5. 异常包装为 EmbeddingError
        """
        if not texts:
            return []

        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._base_url}{self.EMBEDDINGS_ENDPOINT}"

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise EmbeddingError(f"OpenAI Embedding API 请求超时 ({self._timeout}s)")
        except httpx.ConnectError as e:
            raise EmbeddingError(f"OpenAI Embedding API 连接失败: {e}")

        if response.status_code != 200:
            self._raise_http_error(response.status_code, response.text)

        try:
            data = response.json()
            vectors = [item["embedding"] for item in data["data"]]
            return vectors
        except (KeyError, IndexError) as e:
            raise EmbeddingError(f"OpenAI Embedding API 响应解析失败: {e}")

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
            raise EmbeddingError(f"OpenAI Embedding API 认证失败 (401): api_key 无效")
        elif status_code == 429:
            raise EmbeddingError(f"OpenAI Embedding API 速率限制 (429)")
        elif status_code >= 500:
            raise EmbeddingError(f"OpenAI Embedding API 服务器错误 ({status_code})")
        else:
            raise EmbeddingError(f"OpenAI Embedding API 错误 ({status_code}): {body[:200]}")

