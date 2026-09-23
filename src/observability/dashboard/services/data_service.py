"""
DataService — 数据浏览服务

知识点：Dashboard DataService 设计
  - 封装 ChromaStore / ImageStorage 读取操作
  - 提供文档列表、Chunk 详情、图片路径等查询接口
  - 面试考点："为什么用 Service 层？" → 解耦 UI 和数据存储，便于测试和替换

接口签名：
  DataService(chroma_store[, image_storage])
  list_documents(collection?) -> list[DocumentListItem]
  get_document_chunks(source_path) -> list[ChunkDetail]
  get_chunk_metadata(chunk_id) -> dict
  get_image_path(image_id) -> str | None
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DocumentListItem:
    """文档列表项"""
    source_path: str
    doc_id: str = ""
    chunk_count: int = 0
    image_count: int = 0


@dataclass
class ChunkDetail:
    """Chunk 详情"""
    chunk_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class DataService:
    """数据浏览服务 — 封装存储读取操作

    知识点：DataService 的设计原则
      - 只读：不修改数据
      - 封装：隐藏底层存储细节
      - 面试考点："为什么不分页？" → 当前规模小，未来可加 limit/offset
    """

    def __init__(
        self,
        chroma_store: Any,
        image_storage: Any | None = None,
    ) -> None:
        """
        入参：
          - chroma_store: ChromaStore 实例
          - image_storage: ImageStorage 实例（可选）
        """
        self._chroma = chroma_store
        self._image_storage = image_storage

    def list_documents(self) -> list[DocumentListItem]:
        """列出所有已摄入文档

        接口签名：list_documents() -> list[DocumentListItem]
        """
        try:
            records = self._chroma.get_all_records()
        except Exception as e:
            logger.warning("DataService: 读取失败: %s", e)
            return []

        # 按 source 聚合
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
                    "image_count": 0,
                }
            doc_map[source]["chunk_count"] += 1
            img_refs = metadata.get("image_refs", [])
            if isinstance(img_refs, list):
                doc_map[source]["image_count"] += len(img_refs)

        return [DocumentListItem(**info) for info in doc_map.values()]

    def get_document_chunks(self, source_path: str) -> list[ChunkDetail]:
        """获取文档的所有 chunk

        接口签名：get_document_chunks(source_path) -> list[ChunkDetail]
        入参：文档源路径
        出参：ChunkDetail 列表
        """
        try:
            all_records = self._chroma.get_all_records()
        except Exception as e:
            logger.warning("DataService: 读取失败: %s", e)
            return []

        chunks = []
        for record in all_records:
            metadata = record.get("metadata", {})
            source = (
                metadata.get("source")
                or metadata.get("source_ref")
                or "unknown"
            )
            if source == source_path or source_path in record.get("id", ""):
                chunks.append(ChunkDetail(
                    chunk_id=record.get("id", ""),
                    text=record.get("text", ""),
                    metadata=metadata,
                ))

        return chunks

    def get_image_path(self, image_id: str) -> str | None:
        """获取图片路径

        接口签名：get_image_path(image_id) -> str | None
        """
        if self._image_storage is None:
            return None
        try:
            return self._image_storage.get_path(image_id)
        except Exception:
            return None

