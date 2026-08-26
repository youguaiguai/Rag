# Document → Chunks 转换（调用 libs.splitter）
# 知识点：Chunking 是 RAG 的关键环节
#   - 策略选择影响检索质量：太大召回噪音多，太小丢失上下文
#   - 本项目采用 RecursiveCharacterTextSplitter（按 Markdown 结构切分）
#   - Chunk ID 格式：{doc_id}_{index:04d}_{hash}，保证幂等性

from ingestion.chunking.document_chunker import ChunkingError, DocumentChunker

__all__ = [
    "DocumentChunker",
    "ChunkingError",
]

