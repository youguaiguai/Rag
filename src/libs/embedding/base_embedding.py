"""
Embedding 抽象基类 — 可插拔架构的核心

知识点：
  - Embedding 是什么：将文本映射为高维浮点向量，使语义相近的文本在向量空间中距离更近
  - ABC (Abstract Base Class)：Python 标准库提供的抽象基类机制，强制子类实现 embed()
  - 可插拔架构：上层代码只依赖 BaseEmbedding 接口，不关心底层用的是哪个 Provider
  - 工厂模式配合：EmbeddingFactory.create(settings) 根据 provider 字段创建具体实现

关键接口签名（面试必须掌握）：
  BaseEmbedding.embed(texts: list[str]) -> list[list[float]]
    入参：
      - texts: 文本列表，批量处理提高 API 利用率
    出参：向量列表，每个向量是一个 list[float]，维度由模型决定
    异常：子类实现中可能抛出 EmbeddingError

  BaseEmbedding.model_name -> str
    属性：返回当前使用的 Embedding 模型名称（用于日志和追踪）

  BaseEmbedding.dimensions -> int
    属性：返回向量维度（如 text-embedding-3-small = 1536）

设计原则：
  - 接口最小化：只暴露 embed() 一个核心方法 + 两个只读属性
  - 批量处理：embed() 接受 list[str] 而非单个 str，减少 API 调用次数
  - 异常统一：子类应将 Provider 特有的异常转换为 EmbeddingError

面试考点：
  - "Embedding 的作用？" → 将文本转为向量，使语义相似的文本距离更近
  - "为什么要批量 embed？" → 减少 API 调用次数，降低成本和延迟
  - "dimensions 必须与模型匹配？" → 是的，不同模型输出维度不同，不匹配会导致检索错误
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class EmbeddingError(Exception):
    """Embedding 调用异常

    知识点：为什么自定义异常？
      - 统一不同 Provider 的异常类型（OpenAI APIConnectionError、
        Azure AuthenticationError 等都转换为 EmbeddingError）
      - 上层代码只需 except EmbeddingError，不需要关心底层 Provider
      - 面试考点："异常转译模式" — 将底层异常包装为领域异常
    """
    pass


# ============================================================
# BaseEmbedding 抽象基类
# ============================================================

class BaseEmbedding(ABC):
    """Embedding 抽象基类 — 所有 Embedding 实现的统一接口

    接口签名：
      embed(texts: list[str]) -> list[list[float]]
      model_name -> str (property)
      dimensions -> int (property)

    使用方式（上层代码不关心具体 Provider）：
      embedding: BaseEmbedding = EmbeddingFactory.create(settings)
      vectors = embedding.embed(["什么是向量数据库？", "RAG 是什么？"])

    知识点：为什么用 ABC 而不是普通继承？
      - ABC + @abstractmethod 强制子类实现 embed()，忘记实现会 TypeError
      - 普通继承没有这个约束，运行时才发现漏实现
      - 面试考点："ABC 的作用？" → 编译期约束 + 类型安全 + 接口契约
    """

    @abstractmethod
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """将文本列表批量转换为向量

        接口签名：embed(texts: list[str], **kwargs) -> list[list[float]]
        入参：
          - texts: 文本列表，如 ["什么是向量数据库？", "RAG 是什么？"]
          - **kwargs: 可选参数（预留扩展，如 batch_size 等）
        出参：向量列表，每个向量是 list[float]，维度由模型决定
        异常：EmbeddingError — API 调用失败 / 超时 / 认证错误

        知识点：为什么接受 list[str] 而非单个 str？
          - 批量处理是 Embedding 的核心优化策略
          - 减少 API 调用次数 → 降低成本 + 降低延迟
          - OpenAI / Azure / Ollama 等 API 都原生支持批量 embed
          - 面试考点："批量 embed 的好处？" → 省钱 + 省时间 + 减少网络开销

        返回值结构：
          texts = ["hello", "world"]
          vectors = embed(texts)
          # vectors = [[0.01, 0.02, ...], [0.03, 0.04, ...]]
          # len(vectors) == len(texts)
          # len(vectors[0]) == dimensions
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """返回当前使用的 Embedding 模型名称（用于日志和追踪）

        接口签名：model_name -> str (property)
        示例：'text-embedding-3-small', 'text-embedding-ada-002'
        """
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """返回向量维度（用于校验和日志）

        接口签名：dimensions -> int (property)
        示例：1536 (text-embedding-3-small), 3072 (text-embedding-3-large)

        知识点：dimensions 为什么重要？
          - 向量维度必须与向量数据库的 collection 配置一致
          - 维度不匹配会导致写入或检索失败
          - 面试考点："text-embedding-3-small 的维度是多少？" → 1536
        """
        ...

