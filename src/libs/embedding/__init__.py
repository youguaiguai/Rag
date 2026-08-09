"""
Embedding 模块 — 可插拔的文本向量化抽象层

导出：
  - BaseEmbedding: 抽象基类，所有 Embedding 实现的统一接口
  - EmbeddingError: Embedding 调用异常
  - EmbeddingFactory: 工厂类，根据配置创建对应实现
  - FakeEmbedding: 测试桩，不依赖真实 API
"""

from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError

__all__ = [
    "BaseEmbedding",
    "EmbeddingError",
    "EmbeddingFactory",
    "FakeEmbedding",
]

