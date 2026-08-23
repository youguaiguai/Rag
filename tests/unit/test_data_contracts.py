"""C1: Document/Chunk/ChunkRecord 数据契约测试

测试结构：
  1. ID 生成函数测试（4 个）
  2. Document 数据契约测试（5 个）
  3. Chunk 数据契约测试（7 个）
  4. ChunkRecord 数据契约测试（5 个）
  5. 转换函数测试（4 个）
"""

from __future__ import annotations

import pytest
from core.types import (
    Chunk,
    ChunkRecord,
    DataContractError,
    Document,
    chunk_to_record,
    generate_chunk_id,
    generate_doc_id,
    record_to_vector_record,
)
from typing import Any


# ============================================================
# 1. ID 生成函数测试
# ============================================================

class TestGenerateDocId:

    def test_returns_string(self):
        """返回字符串类型"""
        doc_id = generate_doc_id("/path/to/doc.pdf")
        assert isinstance(doc_id, str)

    def test_deterministic(self):
        """相同路径 → 相同 ID"""
        id1 = generate_doc_id("/path/to/doc.pdf")
        id2 = generate_doc_id("/path/to/doc.pdf")
        assert id1 == id2

    def test_different_paths_different_ids(self):
        """不同路径 → 不同 ID"""
        id1 = generate_doc_id("/path/to/doc1.pdf")
        id2 = generate_doc_id("/path/to/doc2.pdf")
        assert id1 != id2

    def test_id_length(self):
        """ID 长度为 16 字符（SHA256 前 16 位）"""
        doc_id = generate_doc_id("/path/to/doc.pdf")
        assert len(doc_id) == 16


# ============================================================
# 2. Document 数据契约测试
# ============================================================

class TestDocumentContract:

    def test_basic_fields(self):
        """基本字段定义正确"""
        doc = Document(
            doc_id="abc123",
            source_path="/path/to/doc.pdf",
            text="文档内容",
            metadata={"title": "测试文档"},
        )
        assert doc.doc_id == "abc123"
        assert doc.source_path == "/path/to/doc.pdf"
        assert doc.text == "文档内容"
        assert doc.metadata == {"title": "测试文档"}

    def test_default_metadata(self):
        """metadata 默认为空 dict"""
        doc = Document(doc_id="d1", source_path="/p", text="text")
        assert doc.metadata == {}
        assert isinstance(doc.metadata, dict)

    def test_metadata_independence(self):
        """不同实例的 metadata 独立（default_factory 不会共享引用）"""
        doc1 = Document(doc_id="d1", source_path="/p", text="t1")
        doc2 = Document(doc_id="d2", source_path="/p", text="t2")
        doc1.metadata["key"] = "value"
        assert "key" not in doc2.metadata

    def test_equality(self):
        """相同字段的 Document 相等"""
        doc1 = Document(doc_id="d1", source_path="/p", text="t", metadata={"a": 1})
        doc2 = Document(doc_id="d1", source_path="/p", text="t", metadata={"a": 1})
        assert doc1 == doc2

    def test_with_rich_metadata(self):
        """完整 metadata 场景"""
        metadata = {
            "doc_type": "pdf",
            "title": "RAG 架构文档",
            "file_hash": "abc123",
            "created_at": "2024-01-01",
            "page_count": 10,
        }
        doc = Document(
            doc_id="d1",
            source_path="/docs/rag.pdf",
            text="# RAG 架构\n\n正文内容",
            metadata=metadata,
        )
        assert doc.metadata["doc_type"] == "pdf"
        assert doc.metadata["page_count"] == 10
        assert "# RAG" in doc.text


# ============================================================
# 3. Chunk 数据契约测试
# ============================================================

class TestChunkContract:

    def test_basic_fields(self):
        """基本字段定义正确"""
        chunk = Chunk(
            chunk_id="d1_0000_abcd1234",
            doc_id="d1",
            text="块文本",
            index=0,
            source_ref="doc.pdf#chunk=0",
            metadata={"source": "doc.pdf"},
        )
        assert chunk.chunk_id == "d1_0000_abcd1234"
        assert chunk.doc_id == "d1"
        assert chunk.text == "块文本"
        assert chunk.index == 0
        assert chunk.source_ref == "doc.pdf#chunk=0"
        assert chunk.metadata == {"source": "doc.pdf"}

    def test_default_metadata(self):
        """metadata 默认为空 dict"""
        chunk = Chunk(chunk_id="c1", doc_id="d1", text="t", index=0)
        assert chunk.metadata == {}
        assert isinstance(chunk.metadata, dict)

    def test_default_image_ids(self):
        """image_ids 默认为空列表"""
        chunk = Chunk(chunk_id="c1", doc_id="d1", text="t", index=0)
        assert chunk.image_ids == []
        assert isinstance(chunk.image_ids, list)

    def test_default_has_unprocessed_images(self):
        """has_unprocessed_images 默认为 False"""
        chunk = Chunk(chunk_id="c1", doc_id="d1", text="t", index=0)
        assert chunk.has_unprocessed_images is False

    def test_metadata_independence(self):
        """不同实例的 metadata 独立"""
        c1 = Chunk(chunk_id="c1", doc_id="d1", text="t", index=0)
        c2 = Chunk(chunk_id="c2", doc_id="d1", text="t", index=1)
        c1.metadata["key"] = "value"
        assert "key" not in c2.metadata

    def test_image_ids_independence(self):
        """不同实例的 image_ids 独立"""
        c1 = Chunk(chunk_id="c1", doc_id="d1", text="t", index=0)
        c2 = Chunk(chunk_id="c2", doc_id="d1", text="t", index=1)
        c1.image_ids.append("img1")
        assert len(c2.image_ids) == 0

    def test_with_images(self):
        """带图片的 Chunk"""
        chunk = Chunk(
            chunk_id="c1",
            doc_id="d1",
            text="包含图片的块",
            index=0,
            image_ids=["img_001", "img_002"],
            has_unprocessed_images=True,
        )
        assert len(chunk.image_ids) == 2
        assert chunk.has_unprocessed_images is True


# ============================================================
# 4. ChunkRecord 数据契约测试
# ============================================================

class TestChunkRecordContract:

    def test_basic_fields(self):
        """基本字段定义正确"""
        record = ChunkRecord(
            chunk_id="d1_0000_abcd1234",
            doc_id="d1",
            text="块文本",
            embedding=[0.1, 0.2, 0.3],
            metadata={"source": "doc.pdf"},
            source_ref="doc.pdf#chunk=0",
        )
        assert record.chunk_id == "d1_0000_abcd1234"
        assert record.doc_id == "d1"
        assert record.text == "块文本"
        assert record.embedding == [0.1, 0.2, 0.3]
        assert record.metadata == {"source": "doc.pdf"}
        assert record.source_ref == "doc.pdf#chunk=0"

    def test_default_metadata(self):
        """metadata 默认为空 dict"""
        record = ChunkRecord(
            chunk_id="c1", doc_id="d1", text="t", embedding=[0.1],
        )
        assert record.metadata == {}
        assert isinstance(record.metadata, dict)

    def test_default_source_ref(self):
        """source_ref 默认为空字符串"""
        record = ChunkRecord(
            chunk_id="c1", doc_id="d1", text="t", embedding=[0.1],
        )
        assert record.source_ref == ""

    def test_metadata_independence(self):
        """不同实例的 metadata 独立"""
        r1 = ChunkRecord(chunk_id="c1", doc_id="d1", text="t", embedding=[0.1])
        r2 = ChunkRecord(chunk_id="c2", doc_id="d1", text="t", embedding=[0.1])
        r1.metadata["key"] = "value"
        assert "key" not in r2.metadata

    def test_equality(self):
        """相同字段的 ChunkRecord 相等"""
        r1 = ChunkRecord(chunk_id="c1", doc_id="d1", text="t", embedding=[0.1], metadata={"a": 1})
        r2 = ChunkRecord(chunk_id="c1", doc_id="d1", text="t", embedding=[0.1], metadata={"a": 1})
        assert r1 == r2


# ============================================================
# 5. 转换函数测试
# ============================================================

class TestChunkToRecord:

    def test_basic_conversion(self):
        """Chunk → ChunkRecord 基本转换"""
        chunk = Chunk(
            chunk_id="d1_0000_abcd1234",
            doc_id="d1",
            text="块文本",
            index=0,
            source_ref="doc.pdf#chunk=0",
            metadata={"source": "doc.pdf", "title": "测试"},
        )
        record = chunk_to_record(chunk, embedding=[0.1, 0.2, 0.3])

        assert record.chunk_id == chunk.chunk_id
        assert record.doc_id == chunk.doc_id
        assert record.text == chunk.text
        assert record.embedding == [0.1, 0.2, 0.3]
        assert record.source_ref == chunk.source_ref
        assert record.metadata == chunk.metadata

    def test_metadata_deep_copy(self):
        """转换后 metadata 是深拷贝，修改不互相影响"""
        chunk = Chunk(
            chunk_id="c1", doc_id="d1", text="t", index=0,
            metadata={"key": "value"},
        )
        record = chunk_to_record(chunk, embedding=[0.1])
        record.metadata["new_key"] = "new_value"
        assert "new_key" not in chunk.metadata

    def test_preserves_all_fields(self):
        """所有字段正确传递"""
        chunk = Chunk(
            chunk_id="c1",
            doc_id="d1",
            text="text content",
            index=5,
            source_ref="doc.pdf#page=3",
            metadata={"page": 3, "section": "intro"},
            image_ids=["img1"],
            has_unprocessed_images=True,
        )
        record = chunk_to_record(chunk, embedding=[0.5, 0.6])

        assert record.chunk_id == "c1"
        assert record.doc_id == "d1"
        assert record.text == "text content"
        assert record.source_ref == "doc.pdf#page=3"
        assert record.metadata["page"] == 3
        # ChunkRecord 不包含 image_ids 和 has_unprocessed_images（它们不是存储字段）
        assert not hasattr(record, "image_ids")
        assert not hasattr(record, "has_unprocessed_images")


class TestRecordToVectorRecord:

    def test_basic_conversion(self):
        """ChunkRecord → VectorRecord 基本转换"""
        record = ChunkRecord(
            chunk_id="d1_0000_abcd1234",
            doc_id="d1",
            text="块文本",
            embedding=[0.1, 0.2, 0.3],
            metadata={"source": "doc.pdf", "title": "测试"},
            source_ref="doc.pdf#chunk=0",
        )
        vr = record_to_vector_record(record)

        assert vr.id == "d1_0000_abcd1234"  # chunk_id → id
        assert vr.embedding == [0.1, 0.2, 0.3]
        assert vr.text == "块文本"
        # doc_id 和 source_ref 被合并到 metadata
        assert vr.metadata["doc_id"] == "d1"
        assert vr.metadata["source_ref"] == "doc.pdf#chunk=0"
        assert vr.metadata["source"] == "doc.pdf"
        assert vr.metadata["title"] == "测试"

    def test_metadata_enriched(self):
        """metadata 包含 doc_id 和 source_ref"""
        record = ChunkRecord(
            chunk_id="c1",
            doc_id="d1",
            text="t",
            embedding=[0.1],
            metadata={"page": 1},
            source_ref="doc.pdf#page=1",
        )
        vr = record_to_vector_record(record)
        assert vr.metadata["doc_id"] == "d1"
        assert vr.metadata["source_ref"] == "doc.pdf#page=1"
        assert vr.metadata["page"] == 1

    def test_metadata_deep_copy(self):
        """转换后 metadata 是深拷贝"""
        record = ChunkRecord(
            chunk_id="c1", doc_id="d1", text="t",
            embedding=[0.1], metadata={"key": "value"},
            source_ref="ref",
        )
        vr = record_to_vector_record(record)
        vr.metadata["new_key"] = "new"
        assert "new_key" not in record.metadata


# ============================================================
# 6. ID 生成策略集成测试
# ============================================================

class TestIDGenerationStrategy:

    def test_chunk_id_format(self):
        """chunk_id 格式：{doc_id}_{index:04d}_{content_hash[:8]}"""
        doc_id = generate_doc_id("/path/to/doc.pdf")
        content = "这是一段测试文本"
        chunk_id = generate_chunk_id(doc_id, 0, content)

        # 格式检查：doc_id_0000_xxxxxxxx
        parts = chunk_id.split("_")
        assert len(parts) == 3
        assert parts[0] == doc_id
        assert parts[1] == "0000"  # 4 位零填充
        assert len(parts[2]) == 8  # content_hash 前 8 位

    def test_chunk_id_index_padding(self):
        """index 用 4 位零填充"""
        doc_id = "test"
        content = "content"
        for i in range(3):
            chunk_id = generate_chunk_id(doc_id, i, content)
            parts = chunk_id.split("_")
            assert parts[1] == f"{i:04d}"

    def test_chunk_id_idempotent(self):
        """相同内容 → 相同 chunk_id（幂等）"""
        doc_id = "test_doc"
        content = "相同的内容"
        id1 = generate_chunk_id(doc_id, 0, content)
        id2 = generate_chunk_id(doc_id, 0, content)
        assert id1 == id2

    def test_chunk_id_content_change(self):
        """内容变更 → chunk_id 变化"""
        doc_id = "test_doc"
        id1 = generate_chunk_id(doc_id, 0, "内容A")
        id2 = generate_chunk_id(doc_id, 0, "内容B")
        assert id1 != id2

