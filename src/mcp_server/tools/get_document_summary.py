"""
get_document_summary — 获取文档摘要信息

知识点：文档摘要让 Client 快速了解文档内容，无需检索全文
  - 接口签名：get_document_summary(doc_id: str) -> dict
  - 从 VectorStore 按 doc_id 查询文档元数据
  - 返回 title / summary / tags 等结构化信息
  - 面试考点："为什么要单独暴露文档摘要？" → 客户端可快速浏览文档列表，无需全文检索
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 工具 Schema
# ============================================================

TOOL_SCHEMA = {
    "description": "获取指定文档的摘要信息（标题、摘要、标签等元数据）。",
    "inputSchema": {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "文档 ID（必填）",
            },
        },
        "required": ["doc_id"],
    },
}


# ============================================================
# 主入口函数
# ============================================================

def get_document_summary(doc_id: str) -> dict[str, Any]:
    """获取文档摘要

    接口签名：get_document_summary(doc_id: str) -> dict
    入参：
      - doc_id: 文档 ID（必填）
    出参：MCP 响应字典
      成功时：
        {
          "content": [{"type": "text", "text": "...markdown..."}],
          "structuredContent": {"doc_id": str, "title": str, "tags": [...], "source": str, ...}
        }
      失败时：
        {
          "content": [{"type": "text", "text": "错误信息"}],
          "isError": True
        }

    处理流程：
      1. 参数校验（doc_id 非空）
      2. 从 VectorStore 查询包含该 doc_id 的 chunks
      3. 提取元数据（title、tags 等）
      4. 构建响应

    面试考点：
      "如何处理不存在的 doc_id？" → 返回 isError=true + 友好提示
      "为什么从 chunks 取元数据而非单独存储？" → chunks 已冗余存储 doc 级元数据（数据一致性）
    """
    # 参数校验
    if not doc_id or not isinstance(doc_id, str) or not doc_id.strip():
        return {
            "content": [{"type": "text", "text": "错误：doc_id 不能为空"}],
            "isError": True,
        }

    doc_id = doc_id.strip()

    # 从 VectorStore 查询（使用 query + metadata filter）
    try:
        from libs.vector_store.base_vector_store import BaseVectorStore
        from libs.vector_store.vector_store_factory import VectorStoreFactory
        from core.settings import Settings

        settings = Settings()
        store: BaseVectorStore = VectorStoreFactory.create(settings.vector_store)

        # 使用零向量 + metadata filter 查询（不需要真正做语义搜索）
        # 生成与 embedding 维度匹配的零向量
        # 默认 384 维（all-MiniLM-L6-v2）
        embedding_dim = getattr(settings.embedding, "dimension", 384)
        zero_vector = [0.0] * embedding_dim

        # 按 doc_id 过滤查询（获取第一个包含该 doc_id 的 chunk）
        results = store.query(
            vector=zero_vector,
            top_k=1,
            filters={"doc_id": doc_id},
        )

        if not results:
            return {
                "content": [{"type": "text", "text": f"未找到文档: {doc_id}"}],
                "isError": True,
            }

        # 从第一条结果提取文档级元数据
        first = results[0]
        metadata = first.metadata
        title = metadata.get("title") or metadata.get("source") or doc_id
        tags = metadata.get("tags", [])
        source = metadata.get("source") or metadata.get("source_ref", "")

        return {
            "content": [{"type": "text", "text": f"**{title}**\n\ntags: {', '.join(tags) if tags else 'N/A'}"}],
            "structuredContent": {
                "doc_id": doc_id,
                "title": title,
                "tags": tags,
                "source": source,
            },
        }

    except Exception as e:
        logger.exception("get_document_summary 执行异常: doc_id=%s, error=%s", doc_id, e)
        return {
            "content": [{"type": "text", "text": f"查询文档时发生错误: {type(e).__name__}"}],
            "isError": True,
        }

