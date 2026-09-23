"""
ResponseBuilder + CitationGenerator 单元测试 — E3: MCP 响应格式化

测试策略：
  - 使用 Mock 检索结果测试响应构建
  - 验证 Markdown 格式和结构化引用
  - 验证无结果时的友好提示
"""

from __future__ import annotations

import json
import pytest
import sys
from pathlib import Path

# 确保 src/ 在路径中
_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from core.response.response_builder import ResponseBuilder
from core.response.citation_generator import CitationGenerator
from core.types import RetrievalResult
from typing import Any


# ============================================================
# TestCitationGenerator — 引用生成器测试
# ============================================================

class TestCitationGenerator:
    """CitationGenerator 测试（6 个测试）"""

    def setup_method(self) -> None:
        self.generator = CitationGenerator()

    def test_generates_citations_from_results(self) -> None:
        """从检索结果生成引用"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.95, text="text", metadata={"source_ref": "doc.md", "page": 1}),
        ]
        citations = self.generator.generate(results)

        assert len(citations) == 1
        assert citations[0]["source"] == "doc.md"
        assert citations[0]["page"] == 1
        assert citations[0]["chunk_id"] == "c1"
        assert citations[0]["score"] == 0.95

    def test_score_rounds_to_4_decimal(self) -> None:
        """score 保留 4 位小数"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.12345678, text="t", metadata={}),
        ]
        citations = self.generator.generate(results)
        assert citations[0]["score"] == 0.1235

    def test_missing_page_is_none(self) -> None:
        """缺失 page 时为 None"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.5, text="t", metadata={}),
        ]
        citations = self.generator.generate(results)
        assert citations[0]["page"] is None

    def test_empty_results_returns_empty_list(self) -> None:
        """空结果返回空引用"""
        assert self.generator.generate([]) == []

    def test_source_fallback_chain(self) -> None:
        """source 回退链: source_ref → source → doc_id → chunk_id"""
        # 只有 source
        results = [RetrievalResult(chunk_id="c1", score=0.5, text="t", metadata={"source": "file.md"})]
        assert self.generator.generate(results)[0]["source"] == "file.md"

        # 只有 doc_id
        results = [RetrievalResult(chunk_id="c2", score=0.5, text="t", metadata={"doc_id": "doc_1"})]
        assert self.generator.generate(results)[0]["source"] == "doc_1"

        # 只有 chunk_id
        results = [RetrievalResult(chunk_id="c3", score=0.5, text="t", metadata={})]
        assert self.generator.generate(results)[0]["source"] == "c3"

    def test_multiple_results(self) -> None:
        """多个结果生成多个引用"""
        results = [
            RetrievalResult(chunk_id=f"c{i}", score=0.9 - i * 0.1, text="t", metadata={"source_ref": f"doc{i}.md"})
            for i in range(3)
        ]
        citations = self.generator.generate(results)
        assert len(citations) == 3
        assert [c["source"] for c in citations] == ["doc0.md", "doc1.md", "doc2.md"]


# ============================================================
# TestResponseBuilder — 响应构建器测试
# ============================================================

class TestResponseBuilder:
    """ResponseBuilder 测试（8 个测试）"""

    def setup_method(self) -> None:
        self.builder = ResponseBuilder()

    def test_build_returns_mcp_format(self) -> None:
        """build 返回 MCP 格式响应"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text="Azure is a cloud platform.", metadata={"source_ref": "azure.md", "title": "Azure Guide"}),
        ]
        response = self.builder.build(results, query="test")

        assert "content" in response
        assert "structuredContent" in response
        assert isinstance(response["content"], list)
        assert isinstance(response["structuredContent"], dict)

    def test_content_has_text_type(self) -> None:
        """content[0] 是 type=text"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text="text", metadata={}),
        ]
        response = self.builder.build(results)

        assert response["content"][0]["type"] == "text"
        assert "text" in response["content"][0]

    def test_structured_content_has_citations(self) -> None:
        """structuredContent 包含 citations"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text="text", metadata={"source_ref": "doc.md"}),
        ]
        response = self.builder.build(results)

        assert "citations" in response["structuredContent"]
        assert len(response["structuredContent"]["citations"]) == 1

    def test_markdown_contains_citation_markers(self) -> None:
        """Markdown 包含引用标注 [1]、[2]"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text="First result", metadata={"source_ref": "doc1.md", "title": "Doc 1"}),
            RetrievalResult(chunk_id="c2", score=0.8, text="Second result", metadata={"source_ref": "doc2.md", "title": "Doc 2"}),
        ]
        response = self.builder.build(results)
        markdown = response["content"][0]["text"]

        assert "[1]" in markdown
        assert "[2]" in markdown

    def test_markdown_contains_text_summary(self) -> None:
        """Markdown 包含文本摘要"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text="This is the full text content.", metadata={}),
        ]
        response = self.builder.build(results)
        markdown = response["content"][0]["text"]

        assert "This is the full text content" in markdown

    def test_empty_results_returns_friendly_message(self) -> None:
        """无结果返回友好提示"""
        response = self.builder.build([], query="nonexistent")

        assert "content" in response
        markdown = response["content"][0]["text"]
        assert "未找到" in markdown or "no results" in markdown.lower()
        assert response["structuredContent"]["citations"] == []

    def test_long_text_is_truncated(self) -> None:
        """长文本被截断"""
        long_text = "A" * 1000
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text=long_text, metadata={}),
        ]
        response = self.builder.build(results)
        markdown = response["content"][0]["text"]

        # 文本应被截断到约 500 字符
        assert len(markdown) < 800  # 允许一些格式字符

    def test_citations_contain_required_fields(self) -> None:
        """引用包含必需字段: source/page/chunk_id/score"""
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text="text", metadata={"source_ref": "doc.md", "page": 5}),
        ]
        response = self.builder.build(results)
        citation = response["structuredContent"]["citations"][0]

        assert "source" in citation
        assert "page" in citation
        assert "chunk_id" in citation
        assert "score" in citation

