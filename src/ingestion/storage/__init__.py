# 存储层 — 将编码结果持久化到不同后端
# 知识点：存储层是摄取链路的最后一环
#   - BM25Indexer (C11)：SparseVector → 倒排索引 → 文件系统
#   - VectorUpserter (C12)：ChunkRecord → 向量数据库
#   - ImageStorage (C13)：图片数据 → 文件存储 + SQLite 索引

from ingestion.storage.bm25_indexer import BM25Indexer
from ingestion.storage.image_storage import ImageStorage, ImageStorageError
from ingestion.storage.vector_upserter import VectorUpserter

__all__ = [
    "BM25Indexer",
    "VectorUpserter",
    "ImageStorage",
    "ImageStorageError",
]

