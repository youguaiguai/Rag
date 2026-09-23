"""
引用生成器 — 从检索结果生成结构化引用列表

知识点：Citation（引用）是 RAG 系统可信赖性的关键
  - 每个回答必须附带信息来源（文档名、页码、段落位置）
  - 让用户能验证答案的可靠性，而非"黑盒输出"
  - 面试考点："为什么需要 Citation？" → 可验证性是 RAG 可信度的基础

Citation 数据结构（MCP structuredContent 标准格式）：
  - source: 来源文件路径/文件名
  - page: 页码（如果有）
  - chunk_id: Chunk ID（用于溯源）
  - score: 相似度分数

接口签名：
  CitationGenerator.generate(retrieval_results: list[RetrievalResult]) -> list[dict]
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# CitationGenerator — 引用生成器
# ============================================================

class CitationGenerator:
    """引用生成器 — 从 RetrievalResult 列表提取结构化引用

    知识点：CitationGenerator 的设计原则
      - 纯函数式：输入检索结果，输出引用列表，无副作用
      - 字段缺失容错：metadata 中某些字段不存在时使用默认值
      - 面试考点："如果 metadata 里没有 page 怎么办？" → 设为 None 或 "N/A"

    接口签名：
      CitationGenerator.generate(retrieval_results) -> list[dict]
    """

    def generate(self, retrieval_results: list[Any]) -> list[dict[str, Any]]:
        """从检索结果生成引用列表

        接口签名：generate(retrieval_results: list[RetrievalResult]) -> list[dict]
        入参：检索结果列表（RetrievalResult）
        出参：引用字典列表，每个包含 source/page/chunk_id/score

        处理逻辑：
          1. 遍历每个检索结果
          2. 从 metadata 提取 source_ref/source → source
          3. 从 metadata 提取 page → page
          4. 取 chunk_id → chunk_id
          5. 取 score → score（保留 4 位小数）
          6. 组装为标准化 dict

        知识点：引用格式选择
          - "source_ref" 通常是相对路径（如 "docs/guide.md#chunk=3"）
          - "source" 通常是文件名（如 "guide.md"）
          - 面试考点："为什么同时保留 path 和 filename？" → path 用于定位，filename 用于展示
        """
        citations: list[dict[str, Any]] = []

        for result in retrieval_results:
            metadata = getattr(result, "metadata", {}) or {}

            # 提取 source（优先 source_ref，其次 source，最后 chunk_id）
            source = (
                metadata.get("source_ref")
                or metadata.get("source")
                or metadata.get("doc_id")
                or result.chunk_id
            )

            # 提取 page（可选）
            page = metadata.get("page")
            if page is None:
                # 尝试从其他字段推断
                page = metadata.get("page_num")

            citation = {
                "source": source,
                "page": page,
                "chunk_id": result.chunk_id,
                "score": round(result.score, 4),
            }
            citations.append(citation)

        logger.debug("CitationGenerator: 生成 %d 条引用", len(citations))
        return citations

