# 稠密向量编码 + 稀疏编码 + 批处理编排
# 知识点：Encoder 是摄取链路的"编码"环节
#   - DenseEncoder (C8)：Chunk.text → embedding → ChunkRecord
#   - SparseEncoder (C9)：Chunk.text → BM25 统计
#   - BatchProcessor (C10)：分 batch 驱动编码

from ingestion.embedding.dense_encoder import DenseEncoder

__all__ = [
    "DenseEncoder",
]

