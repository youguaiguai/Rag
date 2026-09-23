"""
get_document_summary Tool 单元测试 — E5: 文档摘要查询

测试策略：
  - 直接测试 Tool 函数，Mock VectorStore 控制返回结果
  - 验证成功/失败/边界场景
  - 验证不存在 doc_id 返回 isError=true
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# 确保 src/ 在路径中
_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from mcp_server.tools.get_document_summary import get_document_summary, TOOL_SCHEMA


# ============================================================
# 模拟对象
# ============================================================

class MockQueryResult:
    """模拟 QueryResult"""

    def __init__(self, id: str, score: float, text: str, metadata: dict[str, Any]) -> None:
        self.id = id
        self.score = score
        self.text = text
        self.metadata = metadata


def make_mock_store(results: list[MockQueryResult] | None = None) -> Any:
    """创建 Mock VectorStore"""
    mock_store = MagicMock()
    mock_store.query.return_value = results or []
    return mock_store


# patch 目标：模块内的 VectorStoreFactory
_VS_FACTORY_PATH = "libs.vector_store.vector_store_factory.VectorStoreFactory"


# ============================================================
# TestToolSchema — Tool Schema 测试
# ============================================================

class TestToolSchema:
    """Tool Schema 测试（2 个测试）"""

    def test_schema_has_description(self) -> None:
        """TOOL_SCHEMA 包含 description"""
        assert "description" in TOOL_SCHEMA
        assert len(TOOL_SCHEMA["description"]) > 0

    def test_schema_doc_id_is_required(self) -> None:
        """doc_id 是必需参数"""
        assert "doc_id" in TOOL_SCHEMA["inputSchema"]["required"]
        assert "doc_id" in TOOL_SCHEMA["inputSchema"]["properties"]


# ============================================================
# TestGetDocumentSummary — 主功能测试
# ============================================================

class TestGetDocumentSummary:
    """get_document_summary 功能测试（8 个测试）"""

    def test_empty_doc_id_returns_error(self) -> None:
        """空 doc_id 返回错误"""
        result = get_document_summary("")
        assert result.get("isError") is True

    def test_whitespace_doc_id_returns_error(self) -> None:
        """空白 doc_id 返回错误"""
        result = get_document_summary("   ")
        assert result.get("isError") is True

    def test_nonexistent_doc_id_returns_error(self) -> None:
        """不存在的 doc_id 返回错误"""
        mock_store = make_mock_store([])

        with patch(_VS_FACTORY_PATH) as mock_factory:
            mock_factory.create.return_value = mock_store
            result = get_document_summary("nonexistent_doc")

        assert result.get("isError") is True
        assert "未找到" in result["content"][0]["text"]

    def test_existing_doc_returns_summary(self) -> None:
        """存在的 doc_id 返回摘要"""
        mock_results = [
            MockQueryResult(
                id="chunk_001",
                score=0.5,
                text="Document content here...",
                metadata={
                    "doc_id": "doc_123",
                    "title": "Test Document",
                    "tags": ["python", "tutorial"],
                    "source": "test.md",
                },
            ),
        ]
        mock_store = make_mock_store(mock_results)

        with patch(_VS_FACTORY_PATH) as mock_factory:
            mock_factory.create.return_value = mock_store
            result = get_document_summary("doc_123")

        assert result.get("isError") is not True
        assert "structuredContent" in result
        assert result["structuredContent"]["doc_id"] == "doc_123"
        assert result["structuredContent"]["title"] == "Test Document"
        assert "python" in result["structuredContent"]["tags"]

    def test_returns_mcp_format(self) -> None:
        """返回 MCP 格式响应"""
        mock_results = [
            MockQueryResult(
                id="c1", score=0.5, text="text",
                metadata={"doc_id": "d1", "title": "Doc"},
            ),
        ]
        mock_store = make_mock_store(mock_results)

        with patch(_VS_FACTORY_PATH) as mock_factory:
            mock_factory.create.return_value = mock_store
            result = get_document_summary("d1")

        assert "content" in result
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "text"

    def test_markdown_contains_title(self) -> None:
        """Markdown 包含文档标题"""
        mock_results = [
            MockQueryResult(
                id="c1", score=0.5, text="text",
                metadata={"doc_id": "d1", "title": "My Document", "tags": ["test"]},
            ),
        ]
        mock_store = make_mock_store(mock_results)

        with patch(_VS_FACTORY_PATH) as mock_factory:
            mock_factory.create.return_value = mock_store
            result = get_document_summary("d1")

        markdown = result["content"][0]["text"]
        assert "My Document" in markdown

    def test_markdown_contains_tags(self) -> None:
        """Markdown 包含标签"""
        mock_results = [
            MockQueryResult(
                id="c1", score=0.5, text="text",
                metadata={"doc_id": "d1", "title": "Doc", "tags": ["python", "ml"]},
            ),
        ]
        mock_store = make_mock_store(mock_results)

        with patch(_VS_FACTORY_PATH) as mock_factory:
            mock_factory.create.return_value = mock_store
            result = get_document_summary("d1")

        markdown = result["content"][0]["text"]
        assert "python" in markdown
        assert "ml" in markdown

    def test_exception_returns_error(self) -> None:
        """VectorStore 异常时返回错误"""
        mock_store = MagicMock()
        mock_store.query.side_effect = RuntimeError("DB connection failed")

        with patch(_VS_FACTORY_PATH) as mock_factory:
            mock_factory.create.return_value = mock_store
            result = get_document_summary("doc_1")

        assert result.get("isError") is True
        assert "错误" in result["content"][0]["text"]

