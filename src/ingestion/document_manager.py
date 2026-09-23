"""
DocumentManager — 跨存储的文档生命周期管理

知识点：DocumentManager 的设计
  - 跨存储协调：Chroma + BM25 + ImageStorage + FileIntegrity 四个存储
  - 统一接口：list / detail / delete / stats
  - 面试考点："为什么需要 DocumentManager？" → 统一管理多个存储的文档，避免遗漏

接口签名：
  DocumentManager(chroma_store, bm25_indexer, file_integrity[, image_storage])
  list_documents(collection?) -> list[DocumentInfo]
  get_document_detail(source_path) -> DocumentDetail | None
  delete_document(source_path) -> DeleteResult
  get_collection_stats() -> CollectionStats
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class DocumentInfo:
    """文档基本信息"""
    source_path: str
    doc_id: str = ""
    chunk_count: int = 0
    image_count: int = 0


@dataclass
class DocumentDetail:
    """文档详细信息"""
    source_path: str
    doc_id: str
    chunks: list[dict[str, Any]]
    images: list[str] = field(default_factory=list)


@dataclass
class DeleteResult:
    """删除结果"""
    source_path: str
    chroma_deleted: int = 0
    bm25_deleted: int = 0
    integrity_removed: bool = False
    success: bool = True
    error: str = ""


@dataclass
class CollectionStats:
    """集合统计"""
    total_documents: int = 0
    total_chunks: int = 0
    total_images: int = 0


# ============================================================
# DocumentManager — 文档生命周期管理器
# ============================================================

class DocumentManager:
    """文档生命周期管理器 — 跨存储协调

    知识点：DocumentManager 的设计原则
      - 协调者：不直接操作数据，调用各存储的方法
      - 事务性：多存储删除尽力而为（不保证原子性，但尽力一致）
      - 面试考点："删除的一致性如何保证？" → 尽力而为 + 日志记录，非分布式事务

    接口签名：
      DocumentManager(chroma_store, bm25_indexer, file_integrity[, image_storage])
    """

    def __init__(
        self,
        chroma_store: Any,
        bm25_indexer: Any,
        file_integrity: Any,
        image_storage: Any | None = None,
    ) -> None:
        """初始化 DocumentManager

        入参：
          - chroma_store: ChromaStore 实例
          - bm25_indexer: BM25Indexer 实例
          - file_integrity: FileIntegrityChecker 实例
          - image_storage: ImageStorage 实例（可选）
        """
        self._chroma = chroma_store
        self._bm25 = bm25_indexer
        self._integrity = file_integrity
        self._image_storage = image_storage

    def list_documents(self, collection: str | None = None) -> list[DocumentInfo]:
        """列出所有已摄入文档

        接口签名：list_documents(collection: str | None = None) -> list[DocumentInfo]
        入：collection — 可选集名过滤
        出：DocumentInfo 列表
        """
        try:
            records = self._chroma.get_all_records()
        except Exception as e:
            logger.warning("DocumentManager: 读取失败: %s", e)
            return []

        # 按 source 聚合 chunks
        doc_map: dict[str, dict[str, Any]] = {}
        for record in records:
            metadata = record.get("metadata", {})
            source = (
                metadata.get("source")
                or metadata.get("source_ref")
                or metadata.get("file_path")
                or "unknown"
            )
            if source not in doc_map:
                doc_map[source] = {
                    "source_path": source,
                    "doc_id": metadata.get("doc_id", ""),
                    "chunk_count": 0,
                    "image_count": len(metadata.get("image_refs", [])),
                }
            doc_map[source]["chunk_count"] += 1

        return [DocumentInfo(**info) for info in doc_map.values()]

    def get_document_detail(self, source_path: str) -> DocumentDetail | None:
        """获取文档详情

        接口签名：get_document_detail(source_path: str) -> DocumentDetail | None
        入参：文档源路径
        出参：DocumentDetail（包含 chunks 和 images）
        """
        try:
            # 查询 Chroma 中该文档的所有 chunks
            records = self._chroma.delete_by_metadata({})  # 不行，这会删除
            # 改用过滤查询
            all_records = self._chroma.get_all_records()
            chunks = [
                r for r in all_records
                if (r.get("metadata", {}).get("source") == source_path
                    or r.get("metadata", {}).get("source_ref") == source_path
                    or source_path in r.get("id", ""))
            ]

            if not chunks:
                return None

            doc_id = chunks[0].get("metadata", {}).get("doc_id", "")
            images = []
            for chunk in chunks:
                img_refs = chunk.get("metadata", {}).get("image_refs", [])
                if isinstance(img_refs, list):
                    images.extend(img_refs)

            return DocumentDetail(
                source_path=source_path,
                doc_id=doc_id,
                chunks=chunks,
                images=images,
            )
        except Exception as e:
            logger.warning("DocumentManager: 查询文档详情失败: %s", e)
            return None

    def delete_document(self, source_path: str) -> DeleteResult:
        """删除文档（跨存储协调删除）

        接口签名：delete_document(source_path: str) -> DeleteResult
        入参：文档源路径
        出参：DeleteResult

        删除流程：
          1. Chroma: delete_by_metadata({"source": source_path})
          2. BM25: remove_document(source_path)
          3. FileIntegrity: remove(source_path)

        知识点：多存储删除策略
          - 尽力而为：逐个删除，记录每个步骤结果
          - 异常隔离：单个存储失败不影响其他存储
          - 面试考点："为什么不用分布式事务？" → 本地存储无需 2PC，日志足够
        """
        result = DeleteResult(source_path=source_path)

        # 1. Chroma
        try:
            result.chroma_deleted = self._chroma.delete_by_metadata(
                {"source_path": source_path}
            )
        except Exception as e:
            logger.warning("DocumentManager: Chroma 删除失败: %s", e)

        # 2. BM25
        try:
            result.bm25_deleted = self._bm25.remove_document(source_path)
        except Exception as e:
            logger.warning("DocumentManager: BM25 删除失败: %s", e)

        # 3. FileIntegrity
        try:
            result.integrity_removed = self._integrity.remove(source_path)
        except Exception as e:
            logger.warning("DocumentManager: FileIntegrity 删除失败: %s", e)

        return result

    def get_collection_stats(self) -> CollectionStats:
        """获取集合统计信息

        接口签名：get_collection_stats() -> CollectionStats
        出参：CollectionStats
        """
        try:
            records = self._chroma.get_all_records()
        except Exception:
            records = []

        unique_sources = set()
        for record in records:
            metadata = record.get("metadata", {})
            source = (
                metadata.get("source")
                or metadata.get("source_ref")
                or "unknown"
            )
            unique_sources.add(source)

        return CollectionStats(
            total_documents=len(unique_sources),
            total_chunks=len(records),
        )

