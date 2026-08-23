"""
Ollama Embedding 实现 — 通过 httpx 调用 Ollama Embedding API

知识点：
  - Ollama Embedding API：POST {base_url}/api/embeddings
  - 请求格式：{"model": "nomic-embed-text", "prompt": "text"}
  - 响应格式：{"embedding": [0.01, 0.02, ...]}
  - 注意：Ollama 的 Embedding API 一次只处理一条文本（不像 OpenAI 支持批量）
  - 内部通过循环实现批量 embed
  - 面试考点："Ollama 和 OpenAI Embedding 的区别？" → Ollama 不支持批量

接口签名：
  OllamaEmbedding(settings: EmbeddingSettings)
  embed(texts: list[str]) -> list[list[float]]
  model_name -> str (property)
  dimensions -> int (property)

常见 Ollama Embedding 模型：
  - nomic-embed-text：768 维
  - mxbai-embed-large：1024 维
"""

from __future__ import annotations

from typing import Any

import httpx
from core.settings import EmbeddingSettings
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError


class OllamaEmbedding(BaseEmbedding):
    """Ollama Embedding 实现 — 通过 httpx 调用 Ollama Embedding API

    知识点：Ollama Embedding API 特点
      - 一次只处理一条文本（prompt 字段，非 input 列表）
      - 需要在客户端循环实现批量 embed
      - 响应格式：{"embedding": [float, ...]}（不是 data 数组）
      - 面试考点："Ollama 为什么不支持批量？" → API 设计简单，适合本地使用

    性能注意：
      - 批量 embed 时逐条调用，网络开销 = N * 单次延迟
      - 生产环境可考虑并发请求优化
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    EMBEDDINGS_ENDPOINT = "/api/embeddings"
    DEFAULT_TIMEOUT = 60.0

    # 常见 Ollama Embedding 模型维度
    MODEL_DIMENSIONS = {
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "all-minilm": 384,
    }

    def __init__(self, settings: EmbeddingSettings) -> None:
        """初始化 Ollama Embedding

        接口签名：OllamaEmbedding(settings: EmbeddingSettings)
        入参：
          - settings: Embedding 配置（需要 model，base_url 可选）
        异常：EmbeddingError — model 为空
        """
        if not settings.model:
            raise EmbeddingError("Ollama Embedding 初始化失败: model 不能为空")

        self._model = settings.model
        self._base_url = settings.base_url or self.DEFAULT_BASE_URL
        self._timeout = self.DEFAULT_TIMEOUT

        if settings.dimensions > 0:
            self._dimensions = settings.dimensions
        else:
            self._dimensions = self.MODEL_DIMENSIONS.get(settings.model, 768)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """调用 Ollama Embedding API 批量向量化

        接口签名：embed(texts: list[str]) -> list[list[float]]
        入参：
          - texts: 文本列表
        出参：向量列表
        异常：EmbeddingError — API 调用失败

        处理流程：
          1. 空列表 → 返回空列表
          2. 逐条调用 Ollama /api/embeddings
          3. 收集所有向量
          4. 异常包装为 EmbeddingError
        """
        if not texts:
            return []

        vectors: list[list[float]] = []
        headers = {"Content-Type": "application/json"}
        url = f"{self._base_url}{self.EMBEDDINGS_ENDPOINT}"

        try:
            with httpx.Client(timeout=self._timeout) as client:
                for text in texts:
                    payload = {"model": self._model, "prompt": text}
                    response = client.post(url, json=payload, headers=headers)

                    if response.status_code != 200:
                        self._raise_http_error(response.status_code, response.text)

                    try:
                        data = response.json()
                        vectors.append(data["embedding"])
                    except (KeyError, IndexError) as e:
                        raise EmbeddingError(f"Ollama Embedding API 响应解析失败: {e}")
        except httpx.TimeoutException:
            raise EmbeddingError(f"Ollama Embedding API 请求超时 ({self._timeout}s)")
        except httpx.ConnectError:
            raise EmbeddingError(
                f"Ollama Embedding API 连接失败: 无法连接到 {self._base_url}。"
                f"请确认 Ollama 服务已启动。"
            )

        return vectors

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
        if status_code == 404:
            raise EmbeddingError(f"Ollama Embedding API 错误 (404): 模型 '{self._model}' 未找到")
        elif status_code == 400:
            raise EmbeddingError(f"Ollama Embedding API 错误 (400): 请求参数无效")
        elif status_code >= 500:
            raise EmbeddingError(f"Ollama Embedding API 服务器错误 ({status_code})")
        else:
            raise EmbeddingError(f"Ollama Embedding API 错误 ({status_code})")

