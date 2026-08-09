"""
VectorStore 抽象基类 — 可插拔架构的核心

知识点：
  - VectorStore 是什么：向量数据库的统一接口，存储和检索高维向量
  - ABC (Abstract Base Class)：Python 标准库提供的抽象基类机制
  - 可插拔架构：上层代码只依赖 BaseVectorStore 接口，不关心底层用的是 Chroma 还是 Qdrant
  - 工厂模式配合：VectorStoreFactory.create(settings) 根据 backend 字段创建具体实现

关键接口签名（面试必须掌握）：
  BaseVectorStore.upsert(records: list[VectorRecord]) -> None
    入参：records — 向量记录列表，每条包含 id、embedding、text、metadata
    出参：None（幂等写入，相同 id 覆盖旧记录）
    异常：VectorStoreError

  BaseVectorStore.query(vector, top_k, filters) -> list[QueryResult]
    入参：query 向量、top_k 数量、可选 metadata 过滤器
    出参：查询结果列表，每条包含 id、score、text、metadata
    异常：VectorStoreError

  BaseVectorStore.delete(ids) -> int
    入参：要删除的 id 列表
    出参：实际删除的记录数

  BaseVectorStore.get_by_ids(ids) -> list[dict]
    入参：id 列表
    出参：记录列表（包含 text、metadata，不含向量）

  BaseVectorStore.delete_by_metadata(filter) -> int
    入参：metadata 过滤条件
    出参：删除的记录数

设计原则：
  - 接口完整：定义 upsert/query/delete/get_by_ids/delete_by_metadata 五个核心方法
  - 幂等 upsert：相同 id 重复写入不产生重复记录（覆盖旧记录）
  - 统一返回类型：query 返回 QueryResult，get_by_ids 返回 dict

面试考点：
  - "VectorStore 的作用？" → 存储向量 + 语义检索（cosine similarity）
  - "为什么用 Chroma？" → 嵌入式设计，pip install 即可，无需部署
  - "upsert 和 insert 的区别？" → upsert 幂等，相同 id 覆盖；insert 可能产生重复
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class VectorStoreError(Exception):
    """VectorStore 操作异常

    知识点：为什么自定义异常？
      - 统一不同向量数据库的异常类型（ChromaError、QdrantError 等都转换为 VectorStoreError）
      - 上层代码只需 except VectorStoreError，不需要关心底层实现
      - 面试考点："异常转译模式" — 将底层异常包装为领域异常
    """
    pass


# ============================================================
# 数据契约 — 输入/输出类型
# ============================================================

@dataclass
class VectorRecord:
    """向量记录 — upsert 的输入单元

    知识点：为什么用 dataclass 而非 dict？
      - 类型安全：id 是 str，embedding 是 list[float]，有类型提示
      - IDE 补全：record.id, record.embedding 有补全
      - 不可变性：dataclass 默认可变，但字段明确，避免拼写错误

    接口签名：VectorRecord(id: str, embedding: list[float], text: str, metadata: dict)
    字段说明：
      - id: 记录唯一标识（chunk_id），用于幂等 upsert
      - embedding: 向量（维度由 Embedding 模型决定）
      - text: 原始文本（检索时返回给用户）
      - metadata: 元数据（source_path, doc_type, title, chunk_index 等）

    幂等性设计（面试考点）：
      - 相同 id 的 upsert 覆盖旧记录，不产生重复
      - id 生成策略：hash(source_path + chunk_index + content_hash[:8])
      - 内容变更 → content_hash 变化 → id 变化 → 新记录
      - 内容不变 → content_hash 不变 → id 不变 → 覆盖（幂等）
    """
    id: str
    embedding: list[float]
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    """查询结果 — query 的输出单元

    知识点：为什么单独定义返回类型？
      - 统一不同数据库的返回格式（Chroma/Qdrant/Pinecone 返回格式各不同）
      - 上层代码只依赖 QueryResult，不关心底层格式
      - 包含 score 用于后续 RRF 融合和 Rerank

    接口签名：QueryResult(id: str, score: float, text: str, metadata: dict)
    字段说明：
      - id: 记录 ID（chunk_id），用于去重和溯源
      - score: 相似度分数（cosine similarity，越高越相似）
      - text: 匹配的文本片段
      - metadata: 元数据（用于展示和后续过滤）
    """
    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# BaseVectorStore 抽象基类
# ============================================================

class BaseVectorStore(ABC):
    """VectorStore 抽象基类 — 所有向量数据库实现的统一接口

    接口签名：
      upsert(records: list[VectorRecord]) -> None
      query(vector: list[float], top_k: int, filters: dict | None) -> list[QueryResult]
      delete(ids: list[str]) -> int
      get_by_ids(ids: list[str]) -> list[dict]
      delete_by_metadata(filter: dict) -> int

    使用方式（上层代码不关心具体数据库）：
      store: BaseVectorStore = VectorStoreFactory.create(settings)
      store.upsert([VectorRecord(id="chunk_001", embedding=[0.1, ...], text="...", metadata={...})])
      results = store.query(query_vector, top_k=10)

    知识点：为什么用 ABC？
      - ABC + @abstractmethod 强制子类实现所有方法
      - 编译期约束，忘记实现会 TypeError
      - 面试考点："ABC 的作用？" → 编译期约束 + 类型安全 + 接口契约
    """

    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None:
        """批量写入/更新向量记录（幂等）

        接口签名：upsert(records: list[VectorRecord]) -> None
        入参：records — 向量记录列表
        出参：None
        异常：VectorStoreError — 写入失败

        知识点：幂等 upsert
          - 相同 id 的记录覆盖旧记录，不产生重复
          - "upsert" = "update" + "insert"
          - 面试考点："为什么 upsert 而非 insert？" → 幂等性，重复运行不出错
        """
        ...

    @abstractmethod
    def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[QueryResult]:
        """向量相似度检索

        接口签名：query(vector, top_k=10, filters=None) -> list[QueryResult]
        入参：
          - vector: 查询向量（与存储向量同维度）
          - top_k: 返回最相似的 K 条结果
          - filters: metadata 过滤条件（如 {"source": "doc.pdf"}）
        出参：QueryResult 列表，按 score 降序排列
        异常：VectorStoreError — 查询失败

        知识点：cosine similarity
          - 两个向量的夹角余弦值，范围 [-1, 1]
          - 值越接近 1 表示越相似
          - 不受向量长度影响，只关注方向
          - 面试考点："为什么用 cosine 而非欧氏距离？" → 不受向量长度影响
        """
        ...

    @abstractmethod
    def delete(self, ids: list[str]) -> int:
        """按 ID 删除记录

        接口签名：delete(ids: list[str]) -> int
        入参：ids — 要删除的记录 ID 列表
        出参：实际删除的记录数
        异常：VectorStoreError — 删除失败

        知识点：删除操作在 RAG 中的作用
          - 文档更新时删除旧 chunk 的向量
          - 文档下架时删除所有关联向量
          - DocumentManager 协调跨存储删除（Chroma + BM25 + ImageStorage）
        """
        ...

    @abstractmethod
    def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """按 ID 批量获取记录（不含向量）

        接口签名：get_by_ids(ids: list[str]) -> list[dict]
        入参：ids — 记录 ID 列表
        出参：记录列表（每条包含 id、text、metadata，不含 embedding）

        知识点：为什么 get_by_ids 不返回向量？
          - 向量很大（1536 维 float = 6KB），批量返回浪费内存
          - 调用方通常只需要 text 和 metadata，不需要向量
          - SparseRetriever (D3) 用此方法根据 BM25 检索的 chunk_id 获取原文
        """
        ...

    @abstractmethod
    def delete_by_metadata(self, filter: dict[str, Any]) -> int:
        """按 metadata 条件批量删除记录

        接口签名：delete_by_metadata(filter: dict) -> int
        入参：filter — metadata 过滤条件（如 {"source_path": "doc.pdf"}）
        出参：删除的记录数
        异常：VectorStoreError — 删除失败

        知识点：为什么需要按 metadata 删除？
          - DocumentManager (G2) 删除文档时，需要删除该文档的所有 chunk
          - 按 source_path 过滤删除，一次调用删完所有关联记录
          - 面试考点："跨存储一致性" — Chroma + BM25 + ImageStorage 同步删除
        """
        ...

