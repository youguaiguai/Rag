"""
响应构建器 — MCP 响应格式化 + Markdown 生成

知识点：MCP Tool Response 格式（MCP 协议标准）
  MCP 工具返回格式包含两部分：
  1. content: 主内容数组（给 LLM 看的）
     - content[0] = {"type": "text", "text": "..."}  ← Markdown 文本
  2. structuredContent: 结构化数据（给程序消费的）
     - structuredContent.citations = [{source, page, chunk_id, score}]

  面试考点：
    "为什么分 content 和 structuredContent？"
    → content 给 LLM 阅读（Markdown），structuredContent 给程序消费（结构化数据）
    "引用标注 [1] 的作用？"
    → 让 LLM 在生成回答时标注来源，用户可溯源验证

Markdown 生成规则：
  - 每条结果用引用编号 [1]、[2] 标注
  - 包含文本摘要和来源信息
  - 最后附完整引用列表

接口签名：
  ResponseBuilder.build(retrieval_results, query) -> dict
  返回格式：{"content": [{"type": "text", "text": "..."}], "structuredContent": {"citations": [...]}}
"""

from __future__ import annotations

import logging
from core.response.citation_generator import CitationGenerator
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# ResponseBuilder — MCP 响应构建器
# ============================================================

class ResponseBuilder:
    """响应构建器 — 将检索结果转换为 MCP 响应格式

    知识点：ResponseBuilder 的设计原则
      - 单例模式：无需实例化，使用类方法或实例方法均可
      - 零依赖：只依赖 CitationGenerator
      - 纯函数：相同输入 → 相同输出，无副作用
      - 面试考点："为什么用类而不用纯函数？" → 便于扩展（可注入自定义 formatter）

    接口签名：
      ResponseBuilder.build(retrieval_results, query) -> dict
    """

    def __init__(self) -> None:
        """初始化 ResponseBuilder"""
        self._citation_generator = CitationGenerator()

    def build(self, retrieval_results: list[Any], query: str = "") -> dict[str, Any]:
        """构建 MCP 响应

        接口签名：build(retrieval_results: list[RetrievalResult], query: str) -> dict
        入参：
          - retrieval_results: 检索结果列表
          - query: 原始查询（用于日志和调试）
        出参：MCP 响应格式
          {
            "content": [{"type": "text", "text": "...markdown..."}],
            "structuredContent": {"citations": [{source, page, chunk_id, score}, ...]}
          }

        处理流程：
          1. 无结果 → 返回友好提示
          2. 有结果 → 生成 Markdown + 引用列表

        知识点：Markdown 格式设计
          - 每条结果用 [n] 标注（便于 LLM 引用）
          - 包含文本摘要（前 500 字符）
          - 包含来源信息（文件名/路径）
          - 最后附完整引用列表
          - 面试考点："为什么限制文本长度？" → LLM 上下文窗口有限，控制 token 消耗
        """
        if not retrieval_results:
            return self._build_empty_response(query)

        # 生成引用列表
        citations = self._citation_generator.generate(retrieval_results)

        # 生成 Markdown 文本
        markdown = self._build_markdown(retrieval_results, citations)

        return {
            "content": [
                {
                    "type": "text",
                    "text": markdown,
                }
            ],
            "structuredContent": {
                "citations": citations,
            },
        }

    def _build_markdown(
        self,
        retrieval_results: list[Any],
        citations: list[dict[str, Any]],
    ) -> str:
        """生成 Markdown 文本

        接口签名：_build_markdown(retrieval_results, citations) -> str
        入参：检索结果和引用列表
        出参：Markdown 格式字符串

        Markdown 格式：
          ## 检索结果

          [1] **文档标题**
          文本摘要内容...
          *来源: path/to/file.md | 第 N 页*

          [2] **另一个文档**
          ...

          ## 引用
          1. source | page | chunk_id | score
          2. ...
        """
        lines: list[str] = []
        lines.append("## 检索结果")
        lines.append("")

        for i, (result, citation) in enumerate(zip(retrieval_results, citations), start=1):
            # 来源标题
            title = (
                result.metadata.get("title")
                or citation.get("source")
                or result.chunk_id
            )
            lines.append(f"[{i}] **{title}**")
            lines.append("")

            # 文本摘要（限制 500 字符）
            text = result.text.strip()
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(text)
            lines.append("")

            # 来源信息
            source_parts = []
            if citation.get("source"):
                source_parts.append(citation["source"])
            if citation.get("page") is not None:
                source_parts.append(f"p.{citation['page']}")
            source_info = " | ".join(source_parts)
            if source_info:
                lines.append(f"*来源: {source_info} | score={citation['score']:.4f}*")
            else:
                lines.append(f"*score={citation['score']:.4f}*")
            lines.append("")

        # 引用列表
        lines.append("## 引用")
        lines.append("")
        for i, citation in enumerate(citations, start=1):
            parts = [f"[{i}]"]
            parts.append(citation.get("source", "未知"))
            if citation.get("page") is not None:
                parts.append(f"p.{citation['page']}")
            parts.append(f"score={citation['score']:.4f}")
            lines.append(" | ".join(parts))

        return "\n".join(lines)

    def _build_empty_response(self, query: str) -> dict[str, Any]:
        """构建无结果时的友好响应

        接口签名：_build_empty_response(query: str) -> dict
        入参：原始查询
        出参：MCP 格式响应（提示无结果）

        知识点：无结果处理
          - 不返回空数组（让 LLM 难以处理）
          - 给出明确提示 + 建议操作
          - 面试考点："为什么要区分空结果？" → LLM 需要明确信号判断是否有可用信息
        """
        message = (
            f"未找到与 \"{query}\" 相关的文档。\n\n"
            f"**建议**：\n"
            f"- 尝试使用不同的关键词\n"
            f"- 先运行 `python scripts/ingest.py --path <文档路径>` 摄取数据\n"
            f"- 检查结果是否使用了正确的集合名称"
        )

        logger.debug("无检索结果: query=%r", query)

        return {
            "content": [
                {
                    "type": "text",
                    "text": message,
                }
            ],
            "structuredContent": {
                "citations": [],
            },
        }

