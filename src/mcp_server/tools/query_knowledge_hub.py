"""
query_knowledge_hub — 主检索工具（MCP Tool）

知识点：MCP Tool 是 Server 暴露给 Client 的可调用能力
  - 每个工具需要定义：name（名称）、description（描述）、inputSchema（参数 JSON Schema）
  - 通过 ProtocolHandler 路由到具体执行函数
  - 返回 MCP 格式响应（content + structuredContent）

工具职责：
  1. 接收查询参数（query, top_k, collection）
  2. 调用 HybridSearch + Reranker 获取检索结果
  3. 使用 ResponseBuilder 构建 MCP 响应
  4. 返回 MCPToolResult

  - 面试考点："query_knowledge_hub 做了什么？" → 接收查询 → 检索 → 精排 → 格式化输出

工具 Schema（MCP inputSchema）：
  - query: string（必填）— 查询文本
  - top_k: integer（可选，默认 10）— 返回结果数量
  - collection: string（可选）— 限定检索集合

接口签名：
  query_knowledge_hub(query: str, top_k: int = 10, collection: str | None = None) -> dict
  TOOL_SCHEMA: dict — 工具 schema（name/description/inputSchema）
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 工具 Schema
# ============================================================

TOOL_SCHEMA = {
    "description": "在知识库中检索相关文档片段，获取与用户查询相关的信息。",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询文本（必填）",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量（默认 10，最大 50）",
                "default": 10,
            },
            "collection": {
                "type": "string",
                "description": "限定检索集合名称（可选）",
            },
        },
        "required": ["query"],
    },
}


# ============================================================
# 全局组件引用（延迟初始化）
# ============================================================

_hybrid_search: Any = None
_reranker: Any = None


def _ensure_components() -> None:
    """确保组件已初始化（延迟初始化）

    知识点：延迟初始化（Lazy Initialization）
      - 不在模块导入时创建组件（避免启动开销和依赖问题）
      - 第一次调用工具时创建
      - 面试考点："为什么用延迟初始化？" → 避免导入时加载大量依赖 + 测试时可 Mock
    """
    global _hybrid_search, _reranker

    if _hybrid_search is None:
        from core.query_engine.hybrid_search import HybridSearch
        from core.query_engine.dense_retriever import DenseRetriever
        from core.query_engine.fusion import Fusion
        from core.query_engine.query_processor import QueryProcessor
        from core.query_engine.sparse_retriever import SparseRetriever
        from core.query_engine.reranker import CoreReranker
        from core.settings import Settings

        settings = Settings()
        _hybrid_search = HybridSearch(
            settings=settings,
            query_processor=QueryProcessor(settings),
            dense_retriever=DenseRetriever(settings),
            sparse_retriever=SparseRetriever(settings),
            fusion=Fusion(k=60),
        )
        _reranker = CoreReranker(settings)
        logger.info("query_knowledge_hub: 组件初始化完成")


# ============================================================
# 主入口函数
# ============================================================

def query_knowledge_hub(
    query: str,
    top_k: int = 10,
    collection: str | None = None,
) -> dict[str, Any]:
    """在知识库中检索相关文档片段

    接口签名：query_knowledge_hub(query, top_k=10, collection=None) -> dict
    入参：
      - query: 用户查询文本（必填）
      - top_k: 返回结果数量（可选，默认 10）
      - collection: 限定检索集合（可选）
    出参：MCP 响应字典
      {
        "content": [{"type": "text", "text": "...markdown..."}],
        "structuredContent": {"citations": [{source, page, chunk_id, score}, ...]}
      }

    处理流程：
      1. 初始化组件（首次调用）
      2. 构建 filters（collection）
      3. 调用 HybridSearch.search() 获取候选
      4. 调用 CoreReranker.rerank() 精排（如果启用）
      5. 使用 ResponseBuilder 构建 MCP 响应

    知识点：参数归一化
      - top_k 限制在 [1, 50] 范围
      - 空 query 直接返回友好提示
      - 面试考点："为什么限制 top_k 最大值？" → 避免响应过大超出 LLM 上下文窗口
    """
    from core.response.response_builder import ResponseBuilder

    # 参数归一化
    top_k = max(1, min(50, top_k))

    if not query or not query.strip():
        return ResponseBuilder().build([], query="")

    # 确保组件初始化
    _ensure_components()

    # 构建 filters
    filters = {}
    if collection:
        filters["collection"] = collection

    try:
        # 混合检索
        candidates = _hybrid_search.search(
            query=query,
            top_k=top_k * 2 if _reranker.is_enabled else top_k,
            filters=filters if filters else None,
        )

        if not candidates:
            return ResponseBuilder().build([], query=query)

        # Reranker 精排
        if _reranker.is_enabled:
            results = _reranker.rerank(query, candidates[:top_k * 2])
            results = results[:top_k]
        else:
            results = candidates[:top_k]

        # 构建 MCP 响应
        return ResponseBuilder().build(results, query=query)

    except Exception as e:
        logger.exception("query_knowledge_hub 执行异常: %s", e)
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"检索过程中发生错误: {type(e).__name__}。请稍后重试。",
                }
            ],
            "structuredContent": {"citations": []},
        }

