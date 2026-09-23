"""
list_collections Tool 单元测试 — E4: 列出文档集合

测试策略：
  - 使用临时目录模拟 data/documents/ 结构
  - 验证集合名提取和文件计数
  - 验证空目录和不存在目录的处理
"""

from __future__ import annotations

import json
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# 确保 src/ 在路径中
_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from mcp_server.tools.list_collections import list_collections, TOOL_SCHEMA


# ============================================================
# TestToolSchema — Tool Schema 测试
# ============================================================

class TestToolSchema:
    """Tool Schema 测试（2 个测试）"""

    def test_schema_has_description(self) -> None:
        """TOOL_SCHEMA 包含 description"""
        assert "description" in TOOL_SCHEMA
        assert len(TOOL_SCHEMA["description"]) > 0

    def test_schema_has_input_schema(self) -> None:
        """TOOL_SCHEMA 包含 inputSchema"""
        assert "inputSchema" in TOOL_SCHEMA
        assert TOOL_SCHEMA["inputSchema"]["type"] == "object"


# ============================================================
# TestListCollections — 主功能测试
# ============================================================

class TestListCollections:
    """list_collections 功能测试（8 个测试）"""

    def test_returns_mcp_format(self) -> None:
        """返回 MCP 格式响应"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()
            (data_dir / "default").mkdir()
            (data_dir / "project_a").mkdir()

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            assert "content" in response
            assert "structuredContent" in response
            assert isinstance(response["content"], list)
            assert "collections" in response["structuredContent"]

    def test_lists_subdirectories_as_collections(self) -> None:
        """子目录被识别为集合"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()
            (data_dir / "default").mkdir()
            (data_dir / "project_a").mkdir()
            (data_dir / "project_b").mkdir()

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            collections = response["structuredContent"]["collections"]
            collection_names = {c["name"] for c in collections}
            assert collection_names == {"default", "project_a", "project_b"}

    def test_counts_files_per_collection(self) -> None:
        """正确统计每个集合的文件数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()

            default_dir = data_dir / "default"
            default_dir.mkdir()
            (default_dir / "doc1.md").write_text("content 1")
            (default_dir / "doc2.md").write_text("content 2")

            project_dir = data_dir / "project"
            project_dir.mkdir()
            (project_dir / "file.txt").write_text("content")

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            collections = {c["name"]: c["doc_count"] for c in response["structuredContent"]["collections"]}
            assert collections["default"] == 2
            assert collections["project"] == 1

    def test_empty_directory_returns_empty_list(self) -> None:
        """空目录返回空列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            assert response["structuredContent"]["collections"] == []

    def test_nonexistent_directory_returns_empty(self) -> None:
        """不存在的目录返回空列表（不抛异常）"""
        fake_dir = Path("/nonexistent/path/to/documents")

        with patch("mcp_server.tools.list_collections.DATA_DIR", fake_dir):
            response = list_collections()

        assert response["structuredContent"]["collections"] == []

    def test_content_has_text_type(self) -> None:
        """content[0] 是 type=text"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()
            (data_dir / "default").mkdir()

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            assert response["content"][0]["type"] == "text"

    def test_markdown_contains_collection_names(self) -> None:
        """Markdown 包含集合名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()
            (data_dir / "my_collection").mkdir()

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            markdown = response["content"][0]["text"]
            assert "my_collection" in markdown

    def test_empty_shows_hint(self) -> None:
        """无集合时 Markdown 包含提示"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            markdown = response["content"][0]["text"]
            assert "未找到" in markdown or "ingest" in markdown.lower()

    def test_ignores_files_in_root(self) -> None:
        """根目录下的文件不作为集合"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "documents"
            data_dir.mkdir()
            # 根目录下的文件（不是集合）
            (data_dir / "readme.txt").write_text("not a collection")
            # 子目录（集合）
            (data_dir / "default").mkdir()

            with patch("mcp_server.tools.list_collections.DATA_DIR", data_dir):
                response = list_collections()

            collection_names = [c["name"] for c in response["structuredContent"]["collections"]]
            assert collection_names == ["default"]

