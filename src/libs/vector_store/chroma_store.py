"""
ChromaStore — Chroma 向量数据库实现

知识点：
  - 为什么选 Chroma？
    - 嵌入式设计：pip install chromadb 即可，无需部署数据库服务
    - 适合本地开发和快速原型验证
    - Qdrant/Milvus 等需要 Docker 容器，对于本项目太重
  - 面试考点："Chroma 和 Qdrant 的区别？" → Chroma 嵌入式无需部署，Qdrant 需要容器

  - Chroma API 核心操作：
    1. 创建 Client + Collection
    2. collection.upsert(ids, embeddings, documents, metadatas)
    3. collection.query(query_embeddings, n_results, where)
    4. collection.delete(ids) / collection.get(ids)
    5. collection.delete(where=filter)

  - 面试考点："Chroma 的 where 过滤？" → 支持 $eq/$ne/$in 等操作符

接口签名：
  ChromaStore(settings: VectorStoreSettings)
  upsert(records: list[VectorRecord]) -> None
  query(vector, top_k, filters) -> list[QueryResult]
  delete(ids) -> int
  get_by_ids(ids) -> list[dict]
  delete_by_metadata(filter) -> int
"""

from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings
from core.settings import VectorStoreSettings
from libs.vector_store.base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)
from typing import Any


class ChromaStore(BaseVectorStore):
    """Chroma 向量数据库实现

    知识点：ChromaDB 使用模式
      - PersistentClient：持久化到本地磁盘（默认 data/db/chroma/）
      - Collection：类似 SQL 表，存储向量记录
      - 每条记录包含：id, embedding, document(text), metadata
      - 面试考点："Chroma 的持久化？" → PersistentClient 自动写入磁盘

    幂等 upsert 实现：
      - Chroma 的 upsert 天然幂等：相同 id 覆盖旧记录
      - 不需要先 delete 再 insert
      - 面试考点："upsert 和 insert 的区别？" → upsert 幂等，insert 可能重复

    metadata 过滤（where 条件）：
      - Chroma 使用 where 参数进行 metadata 过滤
      - 格式：{"source": "doc.pdf"} 或 {"$and": [...]}
      - 本实现将简单的 {key: value} 转换为 Chroma 的 where 格式
    """

    def __init__(self, settings: VectorStoreSettings) -> None:
        """初始化 ChromaStore

        接口签名：ChromaStore(settings: VectorStoreSettings)
        入参：
          - settings: VectorStore 配置（包含 persist_path, collection_name 等）
        异常：VectorStoreError — 初始化失败
        """
        try:
            self._client = chromadb.PersistentClient(
                path=settings.persist_path,
            )
            self._collection = self._client.get_or_create_collection(
                name="default",
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaStore 初始化失败: {e}")

    def upsert(self, records: list[VectorRecord]) -> None:
        """批量写入/更新向量记录（幂等）

        接口签名：upsert(records: list[VectorRecord]) -> None
        入参：records — 向量记录列表
        异常：VectorStoreError — 写入失败

        知识点：Chroma upsert
          - ids: 记录 ID 列表
          - embeddings: 向量列表
          - documents: 文本列表
          - metadatas: 元数据列表
          - 相同 id 的记录自动覆盖
        """
        if not records:
            return

        try:
            self._collection.upsert(
                ids=[r.id for r in records],
                embeddings=[r.embedding for r in records],
                documents=[r.text for r in records],
                metadatas=[r.metadata for r in records],
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaStore upsert 失败: {e}")

    def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[QueryResult]:
        """向量相似度检索

        接口签名：query(vector, top_k=10, filters=None) -> list[QueryResult]
        入参：
          - vector: 查询向量
          - top_k: 返回最相似的 K 条
          - filters: metadata 过滤条件
        出参：QueryResult 列表，按 score 降序
        异常：VectorStoreError — 查询失败

        知识点：Chroma query
          - query_embeddings: 查询向量
          - n_results: 返回数量
          - where: metadata 过滤
          - 返回 distances（cosine distance = 1 - cosine similarity）
        """
        try:
            # 构造 where 条件
            where = filters if filters else None

            # Chroma 的 query 期望 query_embeddings 是 list[list[float]]
            results = self._collection.query(
                query_embeddings=[vector],
                n_results=top_k,
                where=where,
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaStore query 失败: {e}")

        # 解析 Chroma 响应
        # results 格式: {"ids": [["id1", "id2"]], "distances": [[0.1, 0.2]],
        #                "documents": [["text1", "text2"]], "metadatas": [[{...}, {...}]]}
        query_results: list[QueryResult] = []

        ids = results.get("ids", [[]])
        distances = results.get("distances", [[]])
        documents = results.get("documents", [[]])
        metadatas = results.get("metadatas", [[]])

        if not ids or not ids[0]:
            return []

        for i, record_id in enumerate(ids[0]):
            # Chroma 返回的是 distance（越小越相似）
            # cosine distance = 1 - cosine similarity
            # 转换为 similarity score
            distance = distances[0][i] if i < len(distances[0]) else 1.0
            score = 1.0 - distance  # distance → similarity

            text = documents[0][i] if i < len(documents[0]) else ""
            metadata = metadatas[0][i] if i < len(metadatas[0]) else {}

            query_results.append(QueryResult(
                id=record_id,
                score=score,
                text=text,
                metadata=metadata,
            ))

        return query_results

    def delete(self, ids: list[str]) -> int:
        """按 ID 删除记录

        接口签名：delete(ids: list[str]) -> int
        出参：实际删除的记录数
        """
        if not ids:
            return 0

        try:
            # 先查询存在的 ID
            existing = self._collection.get(ids=ids)
            count = len(existing.get("ids", []))

            self._collection.delete(ids=ids)
            return count
        except Exception as e:
            raise VectorStoreError(f"ChromaStore delete 失败: {e}")

    def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """按 ID 批量获取记录（不含向量）

        接口签名：get_by_ids(ids: list[str]) -> list[dict]
        出参：记录列表（包含 id, text, metadata，不含 embedding）
        """
        if not ids:
            return []

        try:
            results = self._collection.get(ids=ids)
            records: list[dict[str, Any]] = []

            result_ids = results.get("ids", [])
            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])

            for i, record_id in enumerate(result_ids):
                records.append({
                    "id": record_id,
                    "text": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                })

            return records
        except Exception as e:
            raise VectorStoreError(f"ChromaStore get_by_ids 失败: {e}")

    def delete_by_metadata(self, filter: dict[str, Any]) -> int:
        """按 metadata 条件批量删除记录

        接口签名：delete_by_metadata(filter: dict) -> int
        出参：删除的记录数
        """
        if not filter:
            return 0

        try:
            # 先查询符合条件的记录
            results = self._collection.get(where=filter)
            ids_to_delete = results.get("ids", [])
            count = len(ids_to_delete)

            if count > 0:
                self._collection.delete(ids=ids_to_delete)

            return count
        except Exception as e:
            raise VectorStoreError(f"ChromaStore delete_by_metadata 失败: {e}")

    def get_all_records(self, limit: int = 10000) -> list[dict[str, Any]]:
        """获取所有记录（不含向量，用于文档管理）

        接口签名：get_all_records(limit: int = 10000) -> list[dict]
        入参：limit — 最大返回数量
        出参：记录列表（包含 id, text, metadata，不含 embedding）
        """
        try:
            results = self._collection.get(
                include=["documents", "metadatas"],
                limit=limit,
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaStore get_all_records 失败: {e}")

        records = []
        ids = results.get("ids", [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])

        for i, record_id in enumerate(ids):
            records.append({
                "id": record_id,
                "text": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
            })

        return records

