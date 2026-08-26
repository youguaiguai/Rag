"""
DocumentChunker 单元测试 — C4: Splitter 集成

测试策略：
  - 使用 FakeSplitter（已实现于 splitter_factory.py）隔离测试
  - 不依赖真实 LLM / Embedding / 外部服务
  - 验收标准全覆盖：
    1. 配置驱动：不同 chunk_size 产出不同数量 chunk
    2. ID 唯一性：每个 Chunk 的 ID 在文档内唯一
    3. ID 确定性：同一 Document 重复切分产生相同 ID 序列
    4. 元数据完整性：Chunk.metadata 包含 Document.metadata + chunk_index
    5. 图片分发正确性：含 [IMAGE: id] 的 chunk 仅包含引用子集
    6. 溯源链接：所有 Chunk.source_ref 指向父 Document
    7. 类型契约：输出的 Chunk 符合 core.types 定义

测试分类：
  - 基本切分：正常文档切分、chunk 数量、文本内容
  - ID 确定性：重复切分产生相同 ID 序列
  - ID 唯一性：同一文档内 chunk_id 不重复
  - 元数据继承：Document.metadata 字段全部继承
  - chunk_index：序号从 0 开始递增
  - source_ref：指向父文档 source_path + chunk 序号
  - 图片分发：含占位符的 chunk 分发正确子集
  - 图片分发：无占位符的 chunk 不含 images 字段
  - 图片分发：image_refs 与占位符一致
  - 异常处理：空文档、Splitter 异常
  - 配置驱动：不同 chunk_size 产出不同结果
  - 空白片段过滤
  - splitter_name 属性
"""

from __future__ import annotations

import pytest
from core.settings import Settings, SplitterSettings
from core.types import Chunk, Document, generate_doc_id
from ingestion.chunking.document_chunker import ChunkingError, DocumentChunker
from libs.splitter.base_splitter import BaseSplitter, SplitterError
from libs.splitter.splitter_factory import SplitterFactory
from typing import Any


# ============================================================
# Fixture：FakeSplitter 配置
# ============================================================

def _make_settings(chunk_size: int = 100, chunk_overlap: int = 0,
                  provider: str = "fake") -> Settings:
    """创建测试用 Settings（使用 FakeSplitter）"""
    settings = Settings()
    settings.splitter = SplitterSettings(
        provider=provider,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return settings


def _make_document(text: str, source_path: str = "/test/doc.md",
                   metadata: dict[str, Any] | None = None) -> Document:
    """创建测试用 Document"""
    doc_id = generate_doc_id(source_path)
    doc_metadata = {
        "source_path": source_path,
        "doc_type": "markdown",
        "title": "Test Document",
        "file_name": "doc.md",
    }
    if metadata:
        doc_metadata.update(metadata)
    return Document(
        doc_id=doc_id,
        source_path=source_path,
        text=text,
        metadata=doc_metadata,
    )


# ============================================================
# 自定义 Splitter（用于测试异常和精细控制）
# ============================================================

class ControlledSplitter(BaseSplitter):
    """受控 Splitter — 返回原始文本（不切分，便于测试图片分发）"""

    def __init__(self, settings: SplitterSettings) -> None:
        self._provider_name = "controlled"

    def split_text(self, text: str, **kwargs: Any) -> list[str]:
        # 返回原始文本（不切分），每个 chunk 都包含完整文本
        # 这样图片占位符会被保留在 chunk 中，便于测试图片分发
        return [text]

    @property
    def provider_name(self) -> str:
        return self._provider_name


class ErrorSplitter(BaseSplitter):
    """总是抛出异常的 Splitter"""

    def __init__(self, settings: SplitterSettings) -> None:
        self._provider_name = "error"

    def split_text(self, text: str, **kwargs: Any) -> list[str]:
        raise SplitterError("Simulated split error")

    @property
    def provider_name(self) -> str:
        return self._provider_name


class EmptyResultSplitter(BaseSplitter):
    """返回空列表的 Splitter"""

    def __init__(self, settings: SplitterSettings) -> None:
        self._provider_name = "empty"

    def split_text(self, text: str, **kwargs: Any) -> list[str]:
        return []

    @property
    def provider_name(self) -> str:
        return self._provider_name


class WhitespaceSplitter(BaseSplitter):
    """返回含空白片段的 Splitter"""

    def __init__(self, settings: SplitterSettings) -> None:
        self._provider_name = "whitespace"

    def split_text(self, text: str, **kwargs: Any) -> list[str]:
        return ["real_chunk", "   ", "", "another_chunk"]

    @property
    def provider_name(self) -> str:
        return self._provider_name


# ============================================================
# 基本切分测试
# ============================================================

class TestBasicChunking:
    """基本切分功能"""

    def test_split_returns_list_of_chunks(self):
        """切分返回 Chunk 列表"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        doc = _make_document("a" * 200)

        chunks = chunker.split_document(doc)

        assert isinstance(chunks, list)
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_text_matches_splitter_output(self):
        """Chunk 文本与 Splitter 输出一致"""
        settings = _make_settings(chunk_size=50, chunk_overlap=0)
        chunker = DocumentChunker(settings)
        text = "abcdefghij" * 10  # 100 字符
        doc = _make_document(text)

        chunks = chunker.split_document(doc)

        # FakeSplitter chunk_size=50 → 每 chunk 50 字符
        assert len(chunks) == 2
        assert chunks[0].text == text[:50]
        assert chunks[1].text == text[50:100]

    def test_chunk_count_varies_with_size(self):
        """不同 chunk_size 产出不同数量"""
        text = "x" * 300
        doc = _make_document(text)

        chunker_small = DocumentChunker(_make_settings(chunk_size=50))
        chunks_small = chunker_small.split_document(doc)

        chunker_large = DocumentChunker(_make_settings(chunk_size=200))
        chunks_large = chunker_large.split_document(doc)

        assert len(chunks_small) > len(chunks_large)


# ============================================================
# ID 确定性与唯一性
# ============================================================

class TestChunkID:

    def test_id_deterministic(self):
        """同一 Document 重复切分产生相同 ID 序列"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        doc = _make_document("hello world " * 20)

        chunks1 = chunker.split_document(doc)
        chunks2 = chunker.split_document(doc)

        ids1 = [c.chunk_id for c in chunks1]
        ids2 = [c.chunk_id for c in chunks2]

        assert ids1 == ids2

    def test_id_unique_within_document(self):
        """同一文档内 chunk_id 不重复"""
        settings = _make_settings(chunk_size=30)
        chunker = DocumentChunker(settings)
        doc = _make_document("unique content per chunk " * 20)

        chunks = chunker.split_document(doc)
        ids = [c.chunk_id for c in chunks]

        assert len(ids) == len(set(ids))

    def test_id_format(self):
        """Chunk ID 格式：{doc_id}_{index:04d}_{hash8}"""
        settings = _make_settings(chunk_size=100)
        chunker = DocumentChunker(settings)
        doc = _make_document("test text for id format")

        chunks = chunker.split_document(doc)

        for i, chunk in enumerate(chunks):
            parts = chunk.chunk_id.split("_")
            # doc_id(16) + index(4) + hash(8) = 3 parts joined by _
            assert len(parts) == 3
            assert parts[0] == doc.doc_id
            assert int(parts[1]) == i
            assert len(parts[2]) == 8

    def test_id_changes_with_content(self):
        """内容变更 → ID 变化"""
        settings = _make_settings(chunk_size=100)
        chunker = DocumentChunker(settings)

        doc1 = _make_document("content version one", source_path="/test/v1.md")
        doc2 = _make_document("content version two", source_path="/test/v2.md")

        chunks1 = chunker.split_document(doc1)
        chunks2 = chunker.split_document(doc2)

        assert chunks1[0].chunk_id != chunks2[0].chunk_id


# ============================================================
# 元数据继承
# ============================================================

class TestMetadataInheritance:

    def test_metadata_inherits_document_fields(self):
        """Chunk.metadata 包含 Document.metadata 所有字段"""
        settings = _make_settings(chunk_size=100)
        chunker = DocumentChunker(settings)
        doc = _make_document("some text for chunking")

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            assert chunk.metadata["source_path"] == doc.metadata["source_path"]
            assert chunk.metadata["doc_type"] == doc.metadata["doc_type"]
            assert chunk.metadata["title"] == doc.metadata["title"]
            assert chunk.metadata["file_name"] == doc.metadata["file_name"]

    def test_metadata_contains_chunk_index(self):
        """Chunk.metadata 包含 chunk_index 字段"""
        settings = _make_settings(chunk_size=30)
        chunker = DocumentChunker(settings)
        doc = _make_document("a" * 100)

        chunks = chunker.split_document(doc)

        for i, chunk in enumerate(chunks):
            assert chunk.metadata["chunk_index"] == i

    def test_metadata_deep_copy(self):
        """Chunk.metadata 是深拷贝，修改不影响其他 chunk"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        doc = _make_document("text " * 30, metadata={"custom_key": "original"})

        chunks = chunker.split_document(doc)

        chunks[0].metadata["custom_key"] = "modified"
        assert chunks[1].metadata["custom_key"] == "original"


# ============================================================
# source_ref 溯源
# ============================================================

class TestSourceRef:

    def test_source_ref_points_to_document(self):
        """所有 Chunk.source_ref 指向父文档"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        source_path = "/docs/manual.md"
        doc = _make_document("text " * 100, source_path=source_path)

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            assert source_path in chunk.source_ref
            assert chunk.doc_id == doc.doc_id

    def test_source_ref_contains_chunk_index(self):
        """source_ref 包含 chunk 序号"""
        settings = _make_settings(chunk_size=30)
        chunker = DocumentChunker(settings)
        doc = _make_document("data " * 50)

        chunks = chunker.split_document(doc)

        for i, chunk in enumerate(chunks):
            assert f"chunk={i}" in chunk.source_ref


# ============================================================
# 图片分发
# ============================================================

class TestImageDistribution:

    def _make_doc_with_images(self) -> Document:
        """创建含图片引用的 Document"""
        text = (
            "Introduction about the topic.\n\n"
            "[IMAGE: img_001]\n\n"
            "Some explanation text.\n\n"
            "[IMAGE: img_002]\n\n"
            "Conclusion paragraph."
        )
        images = [
            {"image_id": "img_001", "path": "/data/images/img_001.png", "page": 1},
            {"image_id": "img_002", "path": "/data/images/img_002.png", "page": 2},
            {"image_id": "img_003", "path": "/data/images/img_003.png", "page": 3},
        ]
        return _make_document(text, metadata={"images": images})

    def test_chunk_with_image_placeholder_has_images(self):
        """含 [IMAGE: id] 占位符的 chunk 有 images 字段"""
        # 使用 ControlledSplitter 返回完整文本（含占位符）
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        doc = self._make_doc_with_images()

        chunks = chunker.split_document(doc)

        # ControlledSplitter 返回 3 个 chunk，都包含相同文本
        # 每个都应含 images（因为文本含占位符）
        for chunk in chunks:
            assert "images" in chunk.metadata
            assert "image_refs" in chunk.metadata

    def test_chunk_without_placeholder_no_images(self):
        """无占位符的 chunk 不含 images 字段"""
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        doc = _make_document("plain text without any image references")

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            assert "images" not in chunk.metadata
            assert "image_refs" not in chunk.metadata

    def test_image_refs_match_placeholders(self):
        """image_refs 列表与占位符一致"""
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        doc = self._make_doc_with_images()

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            refs = chunk.metadata["image_refs"]
            assert "img_001" in refs
            assert "img_002" in refs
            assert "img_003" not in refs  # img_003 未被引用

    def test_images_subset_only_referenced(self):
        """images 仅包含被引用的图片子集"""
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        doc = self._make_doc_with_images()

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            images = chunk.metadata["images"]
            # 只有 img_001 和 img_002 被引用，img_003 不应出现
            image_ids = [img["image_id"] for img in images]
            assert "img_001" in image_ids
            assert "img_002" in image_ids
            assert "img_003" not in image_ids

    def test_images_not_directly_inherited(self):
        """images 不可被简单整体继承"""
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        # Document 有 3 张图片，但文本只引用了 2 张
        doc = self._make_doc_with_images()

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            if "images" in chunk.metadata:
                # 不应包含全部 3 张图片
                assert len(chunk.metadata["images"]) <= 2

    def test_duplicate_image_refs_deduplicated(self):
        """重复的 [IMAGE: id] 占位符去重"""
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        text = (
            "[IMAGE: img_001]\n"
            "Some text.\n"
            "[IMAGE: img_001]\n"  # 重复引用
        )
        images = [
            {"image_id": "img_001", "path": "/data/images/img_001.png"},
        ]
        doc = _make_document(text, metadata={"images": images})

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            refs = chunk.metadata.get("image_refs", [])
            assert refs.count("img_001") == 1  # 去重

    def test_unknown_image_id_ignored(self):
        """引用不存在的 image_id 时忽略"""
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        text = "[IMAGE: img_999]"  # 不在文档 images 中
        images = [{"image_id": "img_001", "path": "/data/images/img_001.png"}]
        doc = _make_document(text, metadata={"images": images})

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            # img_999 不在 images 中，所以 images 为空
            # 但 image_refs 包含 img_999
            assert chunk.metadata.get("image_refs") == ["img_999"]
            assert chunk.metadata.get("images") == []

    def test_no_images_in_metadata_no_field(self):
        """Document 无 images 字段时，chunk 也不含 images"""
        SplitterFactory.register("controlled", ControlledSplitter)
        settings = _make_settings(provider="controlled")
        chunker = DocumentChunker(settings)
        text = "[IMAGE: img_001]"
        doc = _make_document(text)  # metadata 无 images

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            # 有占位符但没有 images → images 为空列表
            assert "images" in chunk.metadata
            assert chunk.metadata["images"] == []
            assert chunk.metadata["image_refs"] == ["img_001"]


# ============================================================
# 异常处理
# ============================================================

class TestErrorHandling:

    def test_empty_document_raises(self):
        """空文档 → ChunkingError"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        doc = _make_document("")

        with pytest.raises(ChunkingError, match="文本为空"):
            chunker.split_document(doc)

    def test_splitter_error_wrapped(self):
        """Splitter 异常 → ChunkingError"""
        SplitterFactory.register("error_splitter", ErrorSplitter)
        settings = _make_settings(provider="error_splitter")
        chunker = DocumentChunker(settings)
        doc = _make_document("some text")

        with pytest.raises(ChunkingError, match="文本切分失败"):
            chunker.split_document(doc)

    def test_empty_split_result_raises(self):
        """切分结果为空 → ChunkingError"""
        SplitterFactory.register("empty_splitter", EmptyResultSplitter)
        settings = _make_settings(provider="empty_splitter")
        chunker = DocumentChunker(settings)
        doc = _make_document("some text")

        with pytest.raises(ChunkingError, match="切分结果为空"):
            chunker.split_document(doc)

    def test_all_whitespace_chunks_raises(self):
        """所有 chunk 为空白 → ChunkingError"""
        class AllWhitespaceSplitter(BaseSplitter):
            def __init__(self, settings):
                self._provider_name = "all_ws"
            def split_text(self, text, **kwargs):
                return ["   ", "\n\n", ""]
            @property
            def provider_name(self):
                return self._provider_name

        SplitterFactory.register("all_ws", AllWhitespaceSplitter)
        settings = _make_settings(provider="all_ws")
        chunker = DocumentChunker(settings)
        doc = _make_document("some text")

        with pytest.raises(ChunkingError, match="无有效 chunk"):
            chunker.split_document(doc)

    def test_whitespace_chunks_filtered(self):
        """空白片段被过滤，只保留有效 chunk"""
        # WhitespaceSplitter 返回 ["real_chunk", "   ", "", "another_chunk"]
        # "real_chunk" 和 "another_chunk" 不是空白，保留 2 个
        SplitterFactory.register("ws_splitter", WhitespaceSplitter)
        settings = _make_settings(provider="ws_splitter")
        chunker = DocumentChunker(settings)
        doc = _make_document("some text")

        chunks = chunker.split_document(doc)
        assert len(chunks) == 2
        assert chunks[0].text == "real_chunk"
        assert chunks[1].text == "another_chunk"

    def test_unsupported_splitter_raises(self):
        """不支持的 Splitter provider → ChunkingError"""
        settings = _make_settings(provider="nonexistent")
        with pytest.raises(ChunkingError, match="Splitter 创建失败"):
            DocumentChunker(settings)


# ============================================================
# 配置驱动
# ============================================================

class TestConfigDriven:

    def test_chunk_size_affects_count(self):
        """修改 chunk_size 影响 chunk 数量"""
        text = "x" * 300
        doc = _make_document(text)

        chunker1 = DocumentChunker(_make_settings(chunk_size=100))
        chunker2 = DocumentChunker(_make_settings(chunk_size=50))

        chunks1 = chunker1.split_document(doc)
        chunks2 = chunker2.split_document(doc)

        assert len(chunks2) > len(chunks1)

    def test_chunk_overlap_affects_content(self):
        """chunk_overlap 影响 chunk 内容"""
        text = "abcdefghij" * 10  # 100 字符
        doc = _make_document(text)

        chunker_no_overlap = DocumentChunker(_make_settings(chunk_size=50, chunk_overlap=0))
        chunker_with_overlap = DocumentChunker(_make_settings(chunk_size=50, chunk_overlap=10))

        chunks_no = chunker_no_overlap.split_document(doc)
        chunks_with = chunker_with_overlap.split_document(doc)

        # 有 overlap 时 chunk 数量更多
        assert len(chunks_with) >= len(chunks_no)


# ============================================================
# 类型契约
# ============================================================

class TestTypeContract:

    def test_chunk_fields_complete(self):
        """Chunk 对象字段完整"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        doc = _make_document("text " * 30)

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            assert hasattr(chunk, "chunk_id")
            assert hasattr(chunk, "doc_id")
            assert hasattr(chunk, "text")
            assert hasattr(chunk, "index")
            assert hasattr(chunk, "source_ref")
            assert hasattr(chunk, "metadata")
            assert hasattr(chunk, "image_ids")
            assert hasattr(chunk, "has_unprocessed_images")

    def test_chunk_text_non_empty(self):
        """Chunk 文本非空"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        doc = _make_document("content " * 30)

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            assert chunk.text
            assert chunk.text.strip()

    def test_chunk_index_sequential(self):
        """chunk index 从 0 开始递增"""
        settings = _make_settings(chunk_size=30)
        chunker = DocumentChunker(settings)
        doc = _make_document("a" * 100)

        chunks = chunker.split_document(doc)

        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_doc_id_consistency(self):
        """所有 Chunk.doc_id 与父 Document.doc_id 一致"""
        settings = _make_settings(chunk_size=50)
        chunker = DocumentChunker(settings)
        doc = _make_document("text " * 50)

        chunks = chunker.split_document(doc)

        for chunk in chunks:
            assert chunk.doc_id == doc.doc_id


# ============================================================
# 属性测试
# ============================================================

class TestProperties:

    def test_splitter_name(self):
        """splitter_name 返回当前 Splitter 名称"""
        chunker = DocumentChunker(_make_settings(provider="fake"))
        assert chunker.splitter_name == "fake"

    def test_splitter_name_recursive(self):
        """splitter_name 返回 recursive"""
        chunker = DocumentChunker(_make_settings(provider="recursive"))
        assert chunker.splitter_name == "recursive"


# ============================================================
# 完整流程集成测试
# ============================================================

class TestIntegration:

    def test_full_flow_with_recursive_splitter(self):
        """使用 RecursiveSplitter 完整流程"""
        text = (
            "# Document Title\n\n"
            "## Section 1\n\n"
            "This is the first section with some content. "
            "It has multiple sentences to make it long enough.\n\n"
            "## Section 2\n\n"
            "This is the second section. "
            "It also has content for testing.\n\n"
            "## Section 3\n\n"
            "Final section with concluding remarks."
        )
        doc = _make_document(text, source_path="/docs/test.md")
        settings = _make_settings(chunk_size=100, provider="recursive")
        chunker = DocumentChunker(settings)

        chunks = chunker.split_document(doc)

        # 验证基本属性
        assert len(chunks) >= 2
        for i, chunk in enumerate(chunks):
            assert chunk.index == i
            assert chunk.doc_id == doc.doc_id
            assert chunk.source_ref.startswith("/docs/test.md#chunk=")
            assert chunk.metadata["source_path"] == "/docs/test.md"
            assert chunk.metadata["doc_type"] == "markdown"
            assert chunk.metadata["title"] == "Test Document"
            assert chunk.metadata["chunk_index"] == i

    def test_deterministic_with_recursive_splitter(self):
        """RecursiveSplitter 重复切分 ID 确定性"""
        text = "# Title\n\nParagraph one content here.\n\nParagraph two content here.\n\n"
        text += "Paragraph three content here.\n\n"
        text += "Paragraph four with more content to ensure splitting."
        doc = _make_document(text, source_path="/docs/deter.md")

        chunker = DocumentChunker(_make_settings(chunk_size=80, provider="recursive"))

        chunks1 = chunker.split_document(doc)
        chunks2 = chunker.split_document(doc)

        ids1 = [c.chunk_id for c in chunks1]
        ids2 = [c.chunk_id for c in chunks2]
        assert ids1 == ids2

    def test_image_flow_end_to_end(self):
        """图片分端到端测试"""
        SplitterFactory.register("controlled", ControlledSplitter)
        text = (
            "Introduction.\n\n"
            "[IMAGE: fig_01]\n\n"
            "Middle text.\n\n"
            "[IMAGE: fig_02]\n"
            "[IMAGE: fig_01]\n"  # 重复引用
        )
        images = [
            {"image_id": "fig_01", "path": "/images/fig_01.png", "caption": ""},
            {"image_id": "fig_02", "path": "/images/fig_02.png", "caption": ""},
            {"image_id": "fig_03", "path": "/images/fig_03.png", "caption": ""},  # 未引用
        ]
        doc = _make_document(text, metadata={"images": images})

        chunker = DocumentChunker(_make_settings(provider="controlled"))
        chunks = chunker.split_document(doc)

        for chunk in chunks:
            # 所有 chunk 包含相同文本，都有占位符
            refs = chunk.metadata["image_refs"]
            imgs = chunk.metadata["images"]

            # 去重后只有 fig_01 和 fig_02
            assert set(refs) == {"fig_01", "fig_02"}
            assert len(refs) == 2  # 去重后
            assert len(imgs) == 2
            # fig_03 不应出现
            for img in imgs:
                assert img["image_id"] in {"fig_01", "fig_02"}

