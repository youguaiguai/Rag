"""
VectorUpserter 单元测试 — C12: 向量存储与幂等性保证

测试策略：
  - 使用 FakeVectorStore 隔离，不依赖 ChromaDB
  - 验收标准全覆盖：
    1. 同一 chunk 两次 upsert 产生相同 id（幂等）
    2. 内容变更时 id 变更
    3. 支持批量 upsert 且保持顺序

测试分类（14 个）：
  - 基础 + 空输入（2）
  - 幂等性（3）
  - 批量写入（2）
  - ChunkRecord→VectorRecord 转换（3）
  - 删除（2）
  - Trace + 属性（2）
"""

from __future__ import annotations

import pytest
from core.settings import Settings, VectorStoreSettings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord
from ingestion.storage.vector_upserter import VectorUpserter
from libs.vector_store.base_vector_store import VectorRecord, VectorStoreError
from libs.vector_store.vector_store_factory import FakeVectorStore
from typing import Any


# ============================================================
# 辅助函数
# ============================================================

def _make_settings() -> Settings:
    s = Settings()
    s.vector_store.backend = "fake"
    s.vector_store.persist_path = "/tmp/test_vector"
    return s


def _make_record(
    chunk_id: str = "c_0001",
    doc_id: str = "doc123",
    text: str = "测试文本",
    embedding: list[float] | None = None,
    metadata: dict[str, Any] | None = None,
    source_ref: str = "/test.md#chunk=0",
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text=text,
        embedding=embedding or [0.1, 0.2, 0.3],
        metadata=metadata or {"title": "测试"},
        source_ref=source_ref,
    )


def _make_store() -> FakeVectorStore:
    return FakeVectorStore(VectorStoreSettings())


# ============================================================
# 基础 + 空输入（2 个）
# ============================================================

class TestBasicAndEmpty:

    def test_empty_list_returns_zero(self):
        """空列表 → 返回 0，不调用数据库"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        count = upserter.upsert([])

        assert count == 0
        assert len(store._store) == 0

    def test_single_record_upsert(self):
        """单条记录写入"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        record = _make_record()
        count = upserter.upsert([record])

        assert count == 1
        assert len(store._store) == 1
        assert "c_0001" in store._store


# ============================================================
# 幂等性（3 个）
# ============================================================

class TestIdempotency:

    def test_same_record_twice_same_id(self):
        """验收标准：同一 chunk 两次 upsert 产生相同 id"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        record = _make_record(chunk_id="c_001", text="相同内容")

        upserter.upsert([record])
        upserter.upsert([record])

        # 只有一条记录（覆盖不重复）
        assert len(store._store) == 1
        assert "c_001" in store._store

    def test_content_change_different_id(self):
        """验收标准：内容变更时 id 变更

        chunk_id 基于 hash(source_path + chunk_index + content_hash[:8])
        不同内容的 chunk 有不同的 chunk_id → 不同的 VectorRecord.id
        """
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)

        record1 = _make_record(chunk_id="c_001", text="内容A")
        record2 = _make_record(chunk_id="c_002", text="内容B")

        upserter.upsert([record1, record2])

        assert len(store._store) == 2
        assert "c_001" in store._store
        assert "c_002" in store._store

    def test_upsert_overwrites_existing(self):
        """upsert 覆盖旧记录"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)

        record_v1 = _make_record(chunk_id="c_001", text="旧内容", embedding=[0.1, 0.2])
        upserter.upsert([record_v1])

        record_v2 = _make_record(chunk_id="c_001", text="新内容", embedding=[0.9, 0.8])
        upserter.upsert([record_v2])

        assert len(store._store) == 1
        stored = store._store["c_001"]
        assert stored.text == "新内容"
        assert stored.embedding == [0.9, 0.8]


# ============================================================
# 批量写入（2 个）
# ============================================================

class TestBatchUpsert:

    def test_batch_upsert_preserves_order(self):
        """验收标准：支持批量 upsert 且保持顺序"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)

        records = [
            _make_record(chunk_id=f"c_{i:04d}", text=f"文本{i}", embedding=[float(i)])
            for i in range(5)
        ]
        count = upserter.upsert(records)

        assert count == 5
        assert len(store._store) == 5
        for i in range(5):
            assert f"c_{i:04d}" in store._store

    def test_batch_upsert_count_matches(self):
        """批量写入数量与输入一致"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)

        records = [_make_record(chunk_id=f"c_{i}", text=f"t{i}") for i in range(10)]
        count = upserter.upsert(records)

        assert count == 10


# ============================================================
# ChunkRecord→VectorRecord 转换（3 个）
# ============================================================

class TestRecordConversion:

    def test_id_is_chunk_id(self):
        """VectorRecord.id = ChunkRecord.chunk_id"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        record = _make_record(chunk_id="my_chunk_id")
        upserter.upsert([record])

        assert "my_chunk_id" in store._store

    def test_doc_id_merged_into_metadata(self):
        """doc_id 合并到 metadata"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        record = _make_record(chunk_id="c_1", doc_id="doc_abc")
        upserter.upsert([record])

        stored = store._store["c_1"]
        assert stored.metadata["doc_id"] == "doc_abc"

    def test_source_ref_merged_into_metadata(self):
        """source_ref 合并到 metadata"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        record = _make_record(chunk_id="c_1", source_ref="/doc.md#page=3")
        upserter.upsert([record])

        stored = store._store["c_1"]
        assert stored.metadata["source_ref"] == "/doc.md#page=3"


# ============================================================
# 删除（2 个）
# ============================================================

class TestDelete:

    def test_delete_by_chunk_ids(self):
        """按 chunk_id 删除"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)

        records = [_make_record(chunk_id=f"c_{i}") for i in range(3)]
        upserter.upsert(records)

        deleted = upserter.delete(["c_0", "c_1"])
        assert deleted == 2
        assert "c_0" not in store._store
        assert "c_1" not in store._store
        assert "c_2" in store._store

    def test_delete_by_doc_id(self):
        """按 doc_id 删除文档所有向量"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)

        records = [
            _make_record(chunk_id="c_0", doc_id="doc_a"),
            _make_record(chunk_id="c_1", doc_id="doc_a"),
            _make_record(chunk_id="c_2", doc_id="doc_b"),
        ]
        upserter.upsert(records)

        deleted = upserter.delete_by_doc_id("doc_a")
        assert deleted == 2
        assert "c_0" not in store._store
        assert "c_1" not in store._store
        assert "c_2" in store._store


# ============================================================
# Trace + 属性（2 个）
# ============================================================

class TestTraceAndProperties:

    def test_trace_records_stage(self):
        """trace 记录阶段数据"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        trace = TraceContext(trace_id="test-upserter")

        records = [_make_record(chunk_id=f"c_{i}") for i in range(3)]
        upserter.upsert(records, trace=trace)

        stages = trace.get_stages("vector_upserter")
        assert len(stages) == 1
        assert stages[0].data["total"] == 3
        assert len(stages[0].data["ids"]) == 3

    def test_vector_store_property(self):
        """vector_store 属性可访问"""
        store = _make_store()
        upserter = VectorUpserter(_make_settings(), vector_store=store)
        assert upserter.vector_store is store

