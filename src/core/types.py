"""
核心数据类型/契约 — 全链路复用

知识点：types.py 是整个系统的"数据契约中心"
  - Document: 文档对象（text + metadata），摄取链路的起点
  - Chunk: 文档分块（Document 的子集，带位置信息和元数据）
  - ChunkRecord: 带向量的 Chunk（用于向量存储和检索）
  - 所有模块（ingestion/retrieval/mcp）共享同一套数据定义
  - 好处：避免不同模块间的格式转换，保证数据一致性
  - 面试考点："为什么用 dataclass？" → 零依赖 + 类型提示 + IDE 补全

契约中心模式（Contract-Central Pattern）：
  - 所有模块依赖 types.py 中定义的数据结构
  - 修改契约只改一处，所有模块自动适配
  - 面试考点："什么是契约中心？" → 统一数据定义，全链路复用

ID 生成策略（面试必须掌握）：
  chunk_id = f"{doc_id}_{index:04d}_{content_hash[:8]}"
  - doc_id: 文档唯一标识（source_path 的 SHA256 前 16 位）
  - index: 4 位零填充的 chunk 序号（0000-9999）
  - content_hash: chunk 文本内容的 SHA256 前 8 位
  - 幂等性保证：
    - 内容不变 → content_hash 不变 → id 不变 → upsert 覆盖（幂等）
    - 内容变更 → content_hash 变化 → id 变化 → 新记录
    - 面试考点："为什么 ID 包含 content_hash？" → 内容变更时自动生成新 ID，实现增量更新

数据流：
  Document (C1)
    → Chunk (C1, 经 Splitter 切分)
    → ChunkRecord (C1, 经 Embedding 编码)
    → VectorStore.upsert (C12, 写入向量数据库)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class DataContractError(Exception):
    """数据契约异常

    知识点：为什么自定义异常？
      - 当数据契约被违反时（如空文本、无效索引），抛出此异常
      - 上层代码可以精确捕获
      - 面试考点："什么时候抛 DataContractError？" → 数据不满足契约约束
    """
    pass


# ============================================================
# ID 生成工具函数
# ============================================================

def generate_doc_id(source_path: str) -> str:
    """根据源文件路径生成文档 ID

    接口签名：generate_doc_id(source_path: str) -> str
    入参：source_path — 源文件路径
    出参：16 字符的文档 ID（SHA256 前 16 位）

    知识点：为什么用 SHA256 而非文件名？
      - 文件名可能重复（不同目录下同名文件）
      - 文件名可能含特殊字符（空格、中文）
      - SHA256 保证唯一性 + 固定长度
      - 面试考点："为什么不用文件名做 ID？" → 唯一性 + 固定长度
    """
    return hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:16]


def generate_chunk_id(doc_id: str, index: int, content: str) -> str:
    """生成 Chunk ID

    接口签名：generate_chunk_id(doc_id: str, index: int, content: str) -> str
    入参：
      - doc_id: 文档 ID
      - index: chunk 在文档中的序号（0-based）
      - content: chunk 文本内容
    出参：格式 "{doc_id}_{index:04d}_{content_hash[:8]}"

    知识点：ID 生成策略
      - doc_id (16位) + index (4位零填充) + content_hash (8位)
      - 总长度约 30 字符，稳定且可读
      - 幂等性：内容不变 → hash 不变 → id 不变 → upsert 覆盖
      - 面试考点："ID 为什么要包含 content_hash？"
        → 内容变更时自动生成新 ID，实现增量更新
    """
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    return f"{doc_id}_{index:04d}_{content_hash}"


# ============================================================
# Document — 文档对象（摄取链路起点）
# ============================================================

@dataclass
class Document:
    """文档对象 — 表示一个待处理的原始文档

    知识点：Document 的生命周期
      1. BaseLoader 从文件读取 → 生成 Document
      2. DocumentChunker 切分 Document → 生成 list[Chunk]
      3. 每个 Chunk 继承 Document 的 metadata

    接口签名：Document(doc_id: str, source_path: str, text: str, metadata: dict)
    字段说明：
      - doc_id: 文档唯一标识（source_path 的 SHA256 前 16 位）
      - source_path: 源文件路径（用于溯源和增量摄取）
      - text: 文档全文（Markdown 格式，经 BaseLoader 转换）
      - metadata: 文档级元数据（doc_type, title, created_at 等）

    契约约束：
      - doc_id: 非空字符串
      - source_path: 非空字符串
      - text: 非空字符串（空文档应在 Loader 阶段被过滤）
      - metadata: dict 类型（即使为空也必须是 dict）

    面试考点：
      "Document 的 metadata 包含什么？" → doc_type, title, source_path, file_hash 等
      "为什么 text 是 Markdown 格式？" → 统一中间格式，Splitter 友好
    """
    doc_id: str
    source_path: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Chunk — 文档分块（Document 的子集，带位置信息）
# ============================================================

@dataclass
class Chunk:
    """文档分块 — Document 切分后的片段

    知识点：Chunk 的生命周期
      1. DocumentChunker 调用 Splitter 切分 Document.text → 生成 list[Chunk]
      2. Transform 链对 Chunk 进行精化（ChunkRefiner → MetadataEnricher → ImageCaptioner）
      3. Encoder 将 Chunk.text → embedding → 生成 ChunkRecord
      4. VectorUpserter 将 ChunkRecord 写入向量数据库

    接口签名：Chunk(chunk_id, doc_id, text, index, source_ref, metadata, image_ids, has_unprocessed_images)
    字段说明：
      - chunk_id: 块唯一标识（generate_chunk_id 生成）
      - doc_id: 所属文档 ID（溯源用）
      - text: 块文本内容
      - index: 块在文档中的序号（0-based，用于排序）
      - source_ref: 溯源引用（如 "doc.pdf#page=3" 或 "doc.pdf#chunk=5"）
      - metadata: 块级元数据（继承 Document.metadata + Splitter 添加的）
      - image_ids: 块包含的图片 ID 列表（ImageCaptioner 使用）
      - has_unprocessed_images: 是否有未描述的图片（降级标记）

    契约约束：
      - chunk_id: 非空字符串
      - doc_id: 非空字符串
      - text: 非空字符串
      - index: >= 0
      - source_ref: 非空字符串
      - metadata: dict 类型
      - image_ids: list 类型（默认空列表）
      - has_unprocessed_images: bool（默认 False）

    面试考点：
      "Chunk 和 Document 的区别？" → Chunk 带位置信息（index）和溯源（source_ref）
      "has_unprocessed_images 什么时候为 True？" → Vision LLM 不可用时标记
      "为什么有 image_ids？" → 多模态 RAG 中返回图片给用户
    """
    chunk_id: str
    doc_id: str
    text: str
    index: int
    source_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    image_ids: list[str] = field(default_factory=list)
    has_unprocessed_images: bool = False


# ============================================================
# ChunkRecord — 带向量的 Chunk（用于向量存储和检索）
# ============================================================

@dataclass
class ChunkRecord:
    """带向量的 Chunk — Chunk 经 Embedding 编码后的产物

    知识点：ChunkRecord 的生命周期
      1. Encoder 调用 Embedding API 将 Chunk.text → embedding
      2. Chunk + embedding 组合成 ChunkRecord
      3. VectorUpserter 将 ChunkRecord 转换为 VectorRecord 并写入向量数据库
      4. BM25Indexer 用 ChunkRecord.text 构建倒排索引

    接口签名：ChunkRecord(chunk_id, doc_id, text, embedding, metadata, source_ref)
    字段说明：
      - chunk_id: 块唯一标识（与 Chunk.chunk_id 一致，用于幂等 upsert）
      - doc_id: 所属文档 ID
      - text: 块文本内容（用于 BM25 索引和检索时展示）
      - embedding: 向量（维度由 Embedding 模型决定）
      - metadata: 元数据（与 Chunk.metadata 一致）
      - source_ref: 溯源引用

    契约约束：
      - chunk_id: 非空字符串
      - embedding: list[float] 类型
      - text: 非空字符串
      - metadata: dict 类型

    与 VectorRecord 的区别（面试必问）：
      | 维度 | ChunkRecord | VectorRecord |
      |------|-------------|--------------|
      | 用途 | 摄取链路中间产物 | 向量数据库输入单元 |
      | 来源 | Chunk + Embedding | ChunkRecord 转换 |
      | 字段 | chunk_id, doc_id, text, embedding, metadata, source_ref | id, embedding, text, metadata |
      - ChunkRecord → VectorRecord 的转换在 VectorUpserter 中完成

    面试考点：
      "ChunkRecord 和 VectorRecord 的区别？" → ChunkRecord 是摄取链路中间产物，
        VectorRecord 是向量数据库的输入单元，字段略有不同
      "为什么需要两层数据结构？" → 分离业务逻辑和存储逻辑
    """
    chunk_id: str
    doc_id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    source_ref: str = ""


# ============================================================
# 工具函数：Chunk → ChunkRecord 转换
# ============================================================

def chunk_to_record(chunk: Chunk, embedding: list[float]) -> ChunkRecord:
    """将 Chunk + embedding 转换为 ChunkRecord

    接口签名：chunk_to_record(chunk: Chunk, embedding: list[float]) -> ChunkRecord
    入参：
      - chunk: 已切分的 Chunk 对象
      - embedding: Chunk.text 的向量表示
    出参：ChunkRecord 对象

    知识点：转换函数的设计
      - 纯函数：无副作用，输入相同输出相同
      - 字段映射：chunk_id/doc_id/text/metadata/source_ref 直接复制
      - 新增字段：embedding（由 Encoder 提供）
      - 面试考点："为什么要转换？" → Chunk 无向量，ChunkRecord 有向量
    """
    return ChunkRecord(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        text=chunk.text,
        embedding=embedding,
        metadata=dict(chunk.metadata),  # 深拷贝，避免共享引用
        source_ref=chunk.source_ref,
    )


# ============================================================
# 工具函数：ChunkRecord → VectorRecord 转换
# ============================================================

def record_to_vector_record(record: ChunkRecord) -> Any:
    """将 ChunkRecord 转换为 VectorRecord（用于向量数据库写入）

    接口签名：record_to_vector_record(record: ChunkRecord) -> VectorRecord
    入参：ChunkRecord 对象
    出参：VectorRecord 对象

    知识点：转换函数的设计
      - chunk_id → id（字段重命名）
      - embedding → embedding（直接复制）
      - text → text（直接复制）
      - metadata → metadata（合并 doc_id 和 source_ref 到 metadata）
      - 面试考点："为什么把 doc_id 和 source_ref 放入 metadata？"
        → 向量数据库只存 id/embedding/text/metadata，
          doc_id 和 source_ref 需要作为 metadata 用于过滤和溯源

    延迟导入 VectorRecord 避免循环依赖
    """
    from libs.vector_store.base_vector_store import VectorRecord

    # 将 doc_id 和 source_ref 合并到 metadata 中
    enriched_metadata = dict(record.metadata)
    enriched_metadata["doc_id"] = record.doc_id
    enriched_metadata["source_ref"] = record.source_ref

    return VectorRecord(
        id=record.chunk_id,
        embedding=list(record.embedding),
        text=record.text,
        metadata=enriched_metadata,
    )


# ============================================================
# ProcessedQuery — 查询预处理结果（检索链路起点）
# ============================================================

@dataclass
class ProcessedQuery:
    """查询预处理结果 — QueryProcessor.process() 的输出

    知识点：ProcessedQuery 在检索链路中的位置
      1. 用户输入 query 字符串 + 可选 filters
      2. QueryProcessor.process() → 关键词提取 + filters 解析 → ProcessedQuery
      3. ProcessedQuery.keywords → SparseRetriever（BM25 关键词检索）
      4. ProcessedQuery.raw_query → DenseRetriever（语义向量检索）
      5. ProcessedQuery.filters → HybridSearch（metadata 过滤）

    接口签名：ProcessedQuery(raw_query, keywords, filters)
    字段说明：
      - raw_query: 原始查询字符串（DenseRetriever 用于 embedding）
      - keywords: 提取的关键词列表（SparseRetriever 用于 BM25 检索）
      - filters: metadata 过滤条件（HybridSearch 用于向量库过滤）

    契约约束：
      - raw_query: 非空字符串
      - keywords: list[str] 类型（可为空，但通常应非空）
      - filters: dict 类型（即使无过滤条件也是空 dict）

    面试考点：
      "ProcessedQuery 为什么需要 keywords 和 raw_query 两个字段？"
        → keywords 用于 BM25 稀疏检索（精确匹配），raw_query 用于 Dense 稠密检索（语义匹配）
      "filters 是什么？" → metadata 过滤条件，如 {"doc_type": "pdf", "collection": "default"}
    """
    raw_query: str
    keywords: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)

