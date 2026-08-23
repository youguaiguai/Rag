"""C3: Loader 契约测试

测试结构：
  1. BaseLoader ABC 契约测试（3 个）
  2. FakeLoader 测试（4 个）
  3. MarkdownLoader 测试（5 个）
  4. TextLoader 测试（4 个）
  5. PdfLoader 测试（4 个 — 使用 fixtures/sample_documents）
  6. LoaderFactory 工厂路由测试（6 个）
"""

from __future__ import annotations

import pytest
import tempfile
from core.types import Document, generate_doc_id
from libs.loader.base_loader import BaseLoader, LoaderError
from libs.loader.loader_factory import (
    FakeLoader,
    LoaderFactory,
    MarkdownLoader,
    PdfLoader,
    TextLoader,
)
from pathlib import Path
from typing import Any


# ============================================================
# 1. BaseLoader ABC 契约测试
# ============================================================

class TestBaseLoaderContract:

    def test_cannot_instantiate_abc(self):
        """ABC 不能直接实例化"""
        with pytest.raises(TypeError):
            BaseLoader()

    def test_subclass_without_load_fails(self):
        """子类未实现 load() → TypeError"""

        class IncompleteLoader(BaseLoader):
            pass

        with pytest.raises(TypeError):
            IncompleteLoader()

    def test_subclass_with_load_works(self):
        """子类实现 load() → 可实例化"""

        class CompleteLoader(BaseLoader):
            supported_extensions = [".test"]
            def load(self, path: str, **kwargs: Any) -> Document:
                return Document(doc_id="d1", source_path=path, text="test")

        loader = CompleteLoader()
        doc = loader.load("/some/path")
        assert isinstance(doc, Document)


# ============================================================
# 2. FakeLoader 测试
# ============================================================

class TestFakeLoader:

    def test_is_base_loader(self):
        loader = FakeLoader()
        assert isinstance(loader, BaseLoader)

    def test_returns_document(self):
        """返回 Document 对象"""
        loader = FakeLoader()
        doc = loader.load("/fake/path.pdf")
        assert isinstance(doc, Document)

    def test_metadata_contains_required_fields(self):
        """metadata 包含必需字段"""
        loader = FakeLoader()
        doc = loader.load("/fake/path.pdf")
        assert "source_path" in doc.metadata
        assert "doc_type" in doc.metadata
        assert "title" in doc.metadata
        assert doc.metadata["doc_type"] == "fake"

    def test_custom_text(self):
        """自定义文本被正确返回"""
        loader = FakeLoader(text="自定义内容\n\n## 标题")
        doc = loader.load("/fake/path.pdf")
        assert "自定义内容" in doc.text


# ============================================================
# 3. MarkdownLoader 测试
# ============================================================

class TestMarkdownLoader:

    def test_is_base_loader(self):
        loader = MarkdownLoader()
        assert isinstance(loader, BaseLoader)

    def test_load_markdown_file(self):
        """加载 Markdown 文件"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write("# 测试标题\n\n这是正文内容。")
            path = f.name

        try:
            loader = MarkdownLoader()
            doc = loader.load(path)
            assert isinstance(doc, Document)
            assert "# 测试标题" in doc.text
            assert "正文内容" in doc.text
            assert doc.metadata["doc_type"] == "markdown"
            assert doc.metadata["title"] == "测试标题"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_file_not_found(self):
        """文件不存在 → LoaderError"""
        loader = MarkdownLoader()
        with pytest.raises(LoaderError, match="不存在"):
            loader.load("/nonexistent/file.md")

    def test_empty_file(self):
        """空文件 → LoaderError"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("")
            path = f.name
        try:
            loader = MarkdownLoader()
            with pytest.raises(LoaderError, match="为空"):
                loader.load(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_title_fallback_to_filename(self):
        """无标题时用文件名作为 title"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write("没有标题的文档内容")
            path = f.name
        try:
            loader = MarkdownLoader()
            doc = loader.load(path)
            assert doc.metadata["title"] == Path(path).stem
        finally:
            Path(path).unlink(missing_ok=True)


# ============================================================
# 4. TextLoader 测试
# ============================================================

class TestTextLoader:

    def test_is_base_loader(self):
        loader = TextLoader()
        assert isinstance(loader, BaseLoader)

    def test_load_text_file(self):
        """加载文本文件"""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("纯文本内容\n第二行")
            path = f.name
        try:
            loader = TextLoader()
            doc = loader.load(path)
            assert "纯文本内容" in doc.text
            assert doc.metadata["doc_type"] == "text"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_file_not_found(self):
        """文件不存在 → LoaderError"""
        loader = TextLoader()
        with pytest.raises(LoaderError, match="不存在"):
            loader.load("/nonexistent/file.txt")

    def test_empty_file(self):
        """空文件 → LoaderError"""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("")
            path = f.name
        try:
            loader = TextLoader()
            with pytest.raises(LoaderError, match="为空"):
                loader.load(path)
        finally:
            Path(path).unlink(missing_ok=True)


# ============================================================
# 5. PdfLoader 测试（使用 fixtures）
# ============================================================

class TestPdfLoader:

    def test_is_base_loader(self):
        loader = PdfLoader()
        assert isinstance(loader, BaseLoader)

    def test_supported_extensions(self):
        """supported_extensions 包含 .pdf"""
        assert ".pdf" in PdfLoader.supported_extensions

    def test_file_not_found(self):
        """文件不存在 → LoaderError"""
        loader = PdfLoader()
        with pytest.raises(LoaderError, match="不存在"):
            loader.load("/nonexistent/doc.pdf")

    def test_unsupported_extension(self):
        """非 PDF 扩展名 → LoaderError"""
        # 创建一个实际存在的 .txt 文件来测试扩展名检查
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("text")
            path = f.name
        try:
            loader = PdfLoader()
            with pytest.raises(LoaderError, match="不支持"):
                loader.load(path)
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.skipif(
        not Path("tests/fixtures/sample_documents/sample.pdf").exists(),
        reason="sample.pdf not found"
    )
    def test_load_sample_pdf(self):
        """加载 fixtures 中的 sample PDF"""
        loader = PdfLoader()
        doc = loader.load("tests/fixtures/sample_documents/sample.pdf")
        assert isinstance(doc, Document)
        assert len(doc.text) > 0
        assert doc.metadata["doc_type"] == "pdf"
        assert "source_path" in doc.metadata
        assert "title" in doc.metadata

    def test_load_sample_pdf_md(self):
        """加载 fixtures 中的 sample.pdf.md（MarkItDown 输出格式）"""
        md_path = "tests/fixtures/sample_documents/sample.pdf.md"
        if not Path(md_path).exists():
            pytest.skip("sample.pdf.md not found")

        loader = MarkdownLoader()
        doc = loader.load(md_path)
        assert isinstance(doc, Document)
        assert "测试文档标题" in doc.text
        assert "RAG" in doc.text
        assert doc.metadata["title"] == "测试文档标题"


# ============================================================
# 6. LoaderFactory 工厂路由测试
# ============================================================

class TestLoaderFactory:

    def test_create_pdf(self):
        """create("pdf") → PdfLoader"""
        loader = LoaderFactory.create("pdf")
        assert isinstance(loader, PdfLoader)

    def test_create_markdown(self):
        """create("markdown") → MarkdownLoader"""
        loader = LoaderFactory.create("markdown")
        assert isinstance(loader, MarkdownLoader)

    def test_create_text(self):
        """create("text") → TextLoader"""
        loader = LoaderFactory.create("text")
        assert isinstance(loader, TextLoader)

    def test_create_fake(self):
        """create("fake") → FakeLoader"""
        loader = LoaderFactory.create("fake")
        assert isinstance(loader, FakeLoader)

    def test_create_unknown_raises(self):
        """未知类型 → LoaderError"""
        with pytest.raises(LoaderError, match="不支持"):
            LoaderFactory.create("unknown")

    def test_create_for_file_by_extension(self):
        """create_for_file 按扩展名路由"""
        loader = LoaderFactory.create_for_file("/path/to/doc.pdf")
        assert isinstance(loader, PdfLoader)

        loader = LoaderFactory.create_for_file("/path/to/doc.md")
        assert isinstance(loader, MarkdownLoader)

        loader = LoaderFactory.create_for_file("/path/to/doc.txt")
        assert isinstance(loader, TextLoader)

    def test_create_for_file_unsupported(self):
        """不支持的扩展名 → LoaderError"""
        with pytest.raises(LoaderError, match="不支持"):
            LoaderFactory.create_for_file("/path/to/doc.xyz")

    def test_register_custom_loader(self):
        """register() 注册自定义 Loader"""

        class CustomLoader(BaseLoader):
            supported_extensions = [".custom"]
            def load(self, path: str, **kwargs: Any) -> Document:
                return Document(doc_id="d", source_path=path, text="custom")

        LoaderFactory.register("custom", CustomLoader, extensions=[".custom"])

        loader = LoaderFactory.create("custom")
        assert isinstance(loader, CustomLoader)

        loader = LoaderFactory.create_for_file("/path/to/doc.custom")
        assert isinstance(loader, CustomLoader)

