# Transform 链 — Chunk 增强组件（C5-C7）
# 知识点：Transform 是 Pipeline 中的"增强"环节
#   - 原子化：每个 Transform 只做一件事
#   - 幂等性：重复执行结果不变
#   - 降级安全：失败不阻塞 Pipeline，只记录警告
#
# 实现类：
#   - ChunkRefiner (C5)：规则去噪 + 可选 LLM 增强
#   - MetadataEnricher (C6)：title/summary/tags 元数据增强
#   - ImageCaptioner (C7)：Vision LLM 生成图片描述

from ingestion.transform.base_transform import BaseTransform, TransformError
from ingestion.transform.chunk_refiner import ChunkRefiner
from ingestion.transform.image_captioner import ImageCaptioner
from ingestion.transform.metadata_enricher import MetadataEnricher

__all__ = [
    "BaseTransform",
    "TransformError",
    "ChunkRefiner",
    "MetadataEnricher",
    "ImageCaptioner",
]

