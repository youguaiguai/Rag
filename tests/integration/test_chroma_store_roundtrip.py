"""B7.6: ChromaStore Roundtrip 测试

测试结构：
  1. 基本 upsert + query roundtrip（4 个）
  2. top_k 参数测试（2 个）
  3. metadata filters 测试（3 个）
  4. delete 测试（2 个）
  5. get_by_ids 测试（2 个）
  6. delete_by_metadata 测试（2 个）
  7. 工厂路由测试（1 个）

使用临时目录进行持久化测试，测试结束后清理。
"""

from __future__ import annotations

import os
import pytest
import tempfile
from core.settings import VectorStoreSettings
from libs.vector_store.base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)
from libs.vector_store.chroma_store import ChromaStore
from libs.vector_store.vector_store_factory import VectorStoreFactory
from typing import Any


def make_record(
    id: str = "r1",
    embedding: list[float] | None = None,
    text: str = "测试文本",
    metadata: dict[str, Any] | None = None,
) -> VectorRecord:
    if embedding is None:
        embedding = [0.1 * i for i in range(10)]
    if metadata is None:
        metadata = {"source": "doc.pdf", "page": 1}
    return VectorRecord(id=id, embedding=embedding, text=text, metadata=metadata)


@pytest.fixture
def temp_chroma_store():
    """创建临时 ChromaStore 实例（测试后自动清理）

    知识点：pytest fixture + 临时目录
      - 每个测试用独立的临时目录，避免数据污染
      - yield 模式：setup → test → teardown
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ChromaStore(VectorStoreSettings(backend="chroma", persist_path=tmpdir))
        yield store


class TestChromaStoreUpsertQuery:
    """基本 upsert → query roundtrip 测试"""

    def test_upsert_and_query_basic(self, temp_chroma_store):
        """upsert 后能 query 到结果"""
        store = temp_chroma_store
        records = [
            make_record(id="r1", embedding=[1.0, 0.0, 0.0], text="向量数据库"),
            make_record(id="r2", embedding=[0.0, 1.0, 0.0], text="BM25 索引"),
        ]
        store.upsert(records)

        # 查询与 r1 最相似
        results = store.query([1.0, 0.0, 0.0], top_k=2)
        assert len(results) >= 1
        assert results[0].id == "r1"
        assert results[0].text == "向量数据库"

    def test_upsert_idempotent(self, temp_chroma_store):
        """重复 upsert 相同 id 不产生重复"""
        store = temp_chroma_store
        record = make_record(id="r1", embedding=[1.0, 0.0], text="测试")
        store.upsert([record])
        store.upsert([record])  # 再写一次

        results = store.query([1.0, 0.0], top_k=10)
        ids = [r.id for r in results]
        assert ids.count("r1") == 1  # 只有一条

    def test_upsert_empty_list(self, temp_chroma_store):
        """空列表 upsert 不报错"""
        store = temp_chroma_store
        store.upsert([])  # 不应抛异常

    def test_query_returns_query_result(self, temp_chroma_store):
        """query 返回 QueryResult 类型"""
        store = temp_chroma_store
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0], text="hello")])
        results = store.query([1.0, 0.0], top_k=1)
        assert len(results) >= 1
        assert isinstance(results[0], QueryResult)
        assert hasattr(results[0], "id")
        assert hasattr(results[0], "score")
        assert hasattr(results[0], "text")
        assert hasattr(results[0], "metadata")


class TestChromaStoreTopK:

    def test_top_k_limit(self, temp_chroma_store):
        """top_k 限制返回数量"""
        store = temp_chroma_store
        records = [
            make_record(id=f"r{i}", embedding=[float(i), 0.0], text=f"text{i}")
            for i in range(10)
        ]
        store.upsert(records)
        results = store.query([5.0, 0.0], top_k=3)
        assert len(results) <= 3

    def test_top_k_one(self, temp_chroma_store):
        """top_k=1 只返回一条"""
        store = temp_chroma_store
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], text="a"),
            make_record(id="r2", embedding=[0.0, 1.0], text="b"),
        ])
        results = store.query([1.0, 0.0], top_k=1)
        assert len(results) == 1


class TestChromaStoreFilters:

    def test_filter_by_source(self, temp_chroma_store):
        """按 metadata source 过滤"""
        store = temp_chroma_store
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], metadata={"source": "doc1.pdf"}),
            make_record(id="r2", embedding=[0.9, 0.1], metadata={"source": "doc2.pdf"}),
        ])
        results = store.query([1.0, 0.0], top_k=10, filters={"source": "doc1.pdf"})
        assert all(r.metadata.get("source") == "doc1.pdf" for r in results)

    def test_filter_by_page(self, temp_chroma_store):
        """按 metadata page 过滤"""
        store = temp_chroma_store
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], metadata={"page": 1}),
            make_record(id="r2", embedding=[0.9, 0.1], metadata={"page": 2}),
        ])
        results = store.query([1.0, 0.0], top_k=10, filters={"page": 1})
        assert all(r.metadata.get("page") == 1 for r in results)

    def test_no_results_with_filter(self, temp_chroma_store):
        """过滤条件不匹配时返回空"""
        store = temp_chroma_store
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0], metadata={"source": "a.pdf"})])
        results = store.query([1.0, 0.0], top_k=10, filters={"source": "nonexistent.pdf"})
        assert len(results) == 0


class TestChromaStoreDelete:

    def test_delete_by_id(self, temp_chroma_store):
        """按 ID 删除记录"""
        store = temp_chroma_store
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], text="a"),
            make_record(id="r2", embedding=[0.0, 1.0], text="b"),
        ])
        count = store.delete(["r1"])
        assert count == 1
        results = store.query([1.0, 0.0], top_k=10)
        ids = [r.id for r in results]
        assert "r1" not in ids
        assert "r2" in ids

    def test_delete_nonexistent(self, temp_chroma_store):
        """删除不存在的 ID 返回 0"""
        store = temp_chroma_store
        count = store.delete(["nonexistent"])
        assert count == 0


class TestChromaStoreGetByIds:

    def test_get_by_ids(self, temp_chroma_store):
        """按 ID 批量获取"""
        store = temp_chroma_store
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], text="text1", metadata={"page": 1}),
            make_record(id="r2", embedding=[0.0, 1.0], text="text2", metadata={"page": 2}),
        ])
        results = store.get_by_ids(["r1", "r2"])
        assert len(results) == 2
        assert results[0]["text"] in ("text1", "text2")

    def test_get_by_ids_empty(self, temp_chroma_store):
        """空 ID 列表返回空"""
        store = temp_chroma_store
        results = store.get_by_ids([])
        assert results == []


class TestChromaStoreDeleteByMetadata:

    def test_delete_by_source(self, temp_chroma_store):
        """按 source 删除"""
        store = temp_chroma_store
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], metadata={"source": "doc1.pdf"}),
            make_record(id="r2", embedding=[0.0, 1.0], metadata={"source": "doc2.pdf"}),
        ])
        count = store.delete_by_metadata({"source": "doc1.pdf"})
        assert count == 1
        results = store.query([1.0, 0.0], top_k=10)
        ids = [r.id for r in results]
        assert "r1" not in ids
        assert "r2" in ids

    def test_delete_by_metadata_no_match(self, temp_chroma_store):
        """不匹配的 metadata 返回 0"""
        store = temp_chroma_store
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0])])
        count = store.delete_by_metadata({"source": "nonexistent.pdf"})
        assert count == 0


class TestChromaStoreFactory:

    def test_factory_creates_chroma(self):
        """provider=chroma → ChromaStore"""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = VectorStoreSettings(backend="chroma", persist_path=tmpdir)
            store = VectorStoreFactory.create(settings)
            assert isinstance(store, ChromaStore)

