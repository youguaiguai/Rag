"""
VectorStore 契约测试 — 验证接口输入输出 shape

知识点：
  - 契约测试 (Contract Testing)：验证接口的输入输出格式是否符合约定
  - 不测业务逻辑，只测"形状"：返回类型对不对、字段全不全、类型匹配不匹配
  - 与单元测试的区别：单元测试测逻辑正确性，契约测试测接口兼容性

测试覆盖：
  1. BaseVectorStore 抽象约束 — 不能直接实例化
  2. VectorRecord 数据契约 — 字段完整、类型正确
  3. QueryResult 数据契约 — 字段完整、类型正确
  4. FakeVectorStore upsert 契约 — 幂等写入
  5. FakeVectorStore query 契约 — 返回 QueryResult 列表、score 降序
  6. FakeVectorStore delete 契告 — 返回删除数量
  7. FakeVectorStore get_by_ids 契约 — 返回 dict 列表、不含 embedding
  8. FakeVectorStore delete_by_metadata 契约 — 按 metadata 批量删除
  9. VectorStoreFactory 路由 + register 扩展
"""

import math

import pytest
from core.settings import VectorStoreSettings
from libs.vector_store.base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)
from libs.vector_store.vector_store_factory import (
    FakeVectorStore,
    VectorStoreFactory,
)


# ============================================================
# 辅助函数
# ============================================================

def make_record(
    id: str = "chunk_001",
    embedding: list[float] | None = None,
    text: str = "sample text",
    metadata: dict | None = None,
) -> VectorRecord:
    """创建测试用的 VectorRecord"""
    if embedding is None:
        embedding = [1.0, 0.0, 0.0, 0.0]
    if metadata is None:
        metadata = {"source": "doc.pdf", "page": 1}
    return VectorRecord(id=id, embedding=embedding, text=text, metadata=metadata)


# ============================================================
# BaseVectorStore 抽象约束测试
# ============================================================

class TestBaseVectorStoreAbstract:
    """验证 BaseVectorStore 的抽象约束"""

    def test_cannot_instantiate_base_vector_store(self):
        """BaseVectorStore 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError, match="abstract method"):
            BaseVectorStore()  # type: ignore

    def test_subclass_must_implement_upsert(self):
        """子类必须实现 upsert()"""

        class IncompleteStore(BaseVectorStore):
            def query(self, vector, top_k=10, filters=None): return []
            def delete(self, ids): return 0
            def get_by_ids(self, ids): return []
            def delete_by_metadata(self, filter): return 0

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteStore()  # type: ignore

    def test_subclass_must_implement_query(self):
        """子类必须实现 query()"""

        class IncompleteStore2(BaseVectorStore):
            def upsert(self, records): pass
            def delete(self, ids): return 0
            def get_by_ids(self, ids): return []
            def delete_by_metadata(self, filter): return 0

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteStore2()  # type: ignore

    def test_complete_subclass_can_instantiate(self):
        """完整实现所有抽象方法的子类可以实例化"""

        class CompleteStore(BaseVectorStore):
            def upsert(self, records): pass
            def query(self, vector, top_k=10, filters=None): return []
            def delete(self, ids): return 0
            def get_by_ids(self, ids): return []
            def delete_by_metadata(self, filter): return 0

        store = CompleteStore()
        assert store is not None


# ============================================================
# VectorRecord 数据契约测试
# ============================================================

class TestVectorRecordContract:
    """验证 VectorRecord 的数据契约"""

    def test_required_fields(self):
        """VectorRecord 包含所有必需字段"""
        record = VectorRecord(
            id="chunk_001",
            embedding=[0.1, 0.2, 0.3],
            text="hello world",
            metadata={"source": "doc.pdf"},
        )
        assert record.id == "chunk_001"
        assert record.embedding == [0.1, 0.2, 0.3]
        assert record.text == "hello world"
        assert record.metadata == {"source": "doc.pdf"}

    def test_metadata_default_empty_dict(self):
        """metadata 默认为空 dict"""
        record = VectorRecord(id="x", embedding=[1.0], text="t")
        assert record.metadata == {}

    def test_metadata_is_independent_per_instance(self):
        """每个实例的 metadata 是独立的（不共享默认值）"""
        r1 = VectorRecord(id="a", embedding=[1.0], text="t1")
        r2 = VectorRecord(id="b", embedding=[2.0], text="t2")
        r1.metadata["key"] = "value"
        assert "key" not in r2.metadata

    def test_field_types(self):
        """字段类型正确"""
        record = make_record()
        assert isinstance(record.id, str)
        assert isinstance(record.embedding, list)
        assert all(isinstance(x, float) for x in record.embedding)
        assert isinstance(record.text, str)
        assert isinstance(record.metadata, dict)


# ============================================================
# QueryResult 数据契约测试
# ============================================================

class TestQueryResultContract:
    """验证 QueryResult 的数据契约"""

    def test_required_fields(self):
        """QueryResult 包含所有必需字段"""
        result = QueryResult(
            id="chunk_001",
            score=0.95,
            text="hello world",
            metadata={"source": "doc.pdf"},
        )
        assert result.id == "chunk_001"
        assert result.score == 0.95
        assert result.text == "hello world"
        assert result.metadata == {"source": "doc.pdf"}

    def test_metadata_default_empty_dict(self):
        """metadata 默认为空 dict"""
        result = QueryResult(id="x", score=1.0, text="t")
        assert result.metadata == {}

    def test_field_types(self):
        """字段类型正确"""
        result = QueryResult(id="x", score=0.5, text="t", metadata={"k": "v"})
        assert isinstance(result.id, str)
        assert isinstance(result.score, float)
        assert isinstance(result.text, str)
        assert isinstance(result.metadata, dict)


# ============================================================
# FakeVectorStore upsert 契约测试
# ============================================================

class TestFakeVectorStoreUpsertContract:
    """验证 upsert 的输入输出契约"""

    def test_upsert_single_record(self):
        """upsert 单条记录后可以查询到"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        record = make_record(id="r1", embedding=[1.0, 0.0, 0.0])

        store.upsert([record])
        results = store.query([1.0, 0.0, 0.0], top_k=10)

        assert len(results) == 1
        assert results[0].id == "r1"

    def test_upsert_multiple_records(self):
        """upsert 多条记录后全部可查询"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        records = [
            make_record(id="r1", embedding=[1.0, 0.0, 0.0], text="text1"),
            make_record(id="r2", embedding=[0.0, 1.0, 0.0], text="text2"),
            make_record(id="r3", embedding=[0.0, 0.0, 1.0], text="text3"),
        ]

        store.upsert(records)
        results = store.query([1.0, 0.0, 0.0], top_k=10)

        assert len(results) == 3
        ids = {r.id for r in results}
        assert ids == {"r1", "r2", "r3"}

    def test_upsert_idempotent(self):
        """相同 id 的 upsert 覆盖旧记录（幂等性）"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)

        # 第一次写入
        store.upsert([make_record(id="r1", text="old text", embedding=[1.0, 0.0])])
        assert store.count == 1

        # 相同 id 再次写入（内容不同）
        store.upsert([make_record(id="r1", text="new text", embedding=[1.0, 0.0])])
        assert store.count == 1  # 仍然是 1 条，不是 2 条

        # 验证内容被覆盖
        results = store.query([1.0, 0.0], top_k=10)
        assert results[0].text == "new text"

    def test_upsert_empty_list(self):
        """空列表 upsert 不报错"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([])
        assert store.count == 0


# ============================================================
# FakeVectorStore query 契约测试
# ============================================================

class TestFakeVectorStoreQueryContract:
    """验证 query 的输入输出契约"""

    def test_query_returns_query_result_list(self):
        """query 返回 list[QueryResult]"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0, 0.0])])

        results = store.query([1.0, 0.0, 0.0], top_k=10)

        assert isinstance(results, list)
        assert all(isinstance(r, QueryResult) for r in results)

    def test_query_result_has_all_fields(self):
        """每条 QueryResult 包含 id/score/text/metadata"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0, 0.0], text="hello", metadata={"page": 1, "source": "doc.pdf"})
        ])

        results = store.query([1.0, 0.0, 0.0], top_k=10)
        r = results[0]

        assert hasattr(r, "id")
        assert hasattr(r, "score")
        assert hasattr(r, "text")
        assert hasattr(r, "metadata")
        assert r.id == "r1"
        assert isinstance(r.score, float)
        assert r.text == "hello"
        assert r.metadata == {"page": 1, "source": "doc.pdf"}

    def test_query_results_sorted_by_score_desc(self):
        """query 结果按 score 降序排列"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0, 0.0]),   # cos=1.0 with [1,0,0]
            make_record(id="r2", embedding=[0.7, 0.7, 0.0]),    # cos≈0.707
            make_record(id="r3", embedding=[0.0, 1.0, 0.0]),    # cos=0.0
        ])

        results = store.query([1.0, 0.0, 0.0], top_k=10)

        assert results[0].id == "r1"
        assert results[0].score > results[1].score
        assert results[1].score > results[2].score

    def test_query_top_k_limit(self):
        """top_k 限制返回数量"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id=f"r{i}", embedding=[float(i), 0.0, 0.0])
            for i in range(10)
        ])

        results = store.query([1.0, 0.0, 0.0], top_k=3)
        assert len(results) == 3

    def test_query_empty_store(self):
        """空库查询返回空列表"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        results = store.query([1.0, 0.0, 0.0], top_k=10)
        assert results == []

    def test_query_with_metadata_filter(self):
        """metadata 过滤 — 只返回匹配的记录"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], metadata={"source": "a.pdf"}),
            make_record(id="r2", embedding=[1.0, 0.0], metadata={"source": "b.pdf"}),
            make_record(id="r3", embedding=[1.0, 0.0], metadata={"source": "a.pdf"}),
        ])

        results = store.query([1.0, 0.0], top_k=10, filters={"source": "a.pdf"})
        assert len(results) == 2
        assert all(r.metadata["source"] == "a.pdf" for r in results)

    def test_query_with_multiple_filters(self):
        """多条件 metadata 过滤 — AND 逻辑"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], metadata={"source": "a.pdf", "page": 1}),
            make_record(id="r2", embedding=[1.0, 0.0], metadata={"source": "a.pdf", "page": 2}),
            make_record(id="r3", embedding=[1.0, 0.0], metadata={"source": "b.pdf", "page": 1}),
        ])

        results = store.query([1.0, 0.0], top_k=10, filters={"source": "a.pdf", "page": 1})
        assert len(results) == 1
        assert results[0].id == "r1"

    def test_query_no_filter_match(self):
        """filter 不匹配任何记录 → 返回空列表"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0], metadata={"source": "a.pdf"})])

        results = store.query([1.0, 0.0], top_k=10, filters={"source": "nonexistent.pdf"})
        assert results == []

    def test_query_score_range(self):
        """score 在 [-1, 1] 范围内（cosine similarity 值域）"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0, 0.0]),
            make_record(id="r2", embedding=[0.0, 1.0, 0.0]),
        ])

        results = store.query([0.7, 0.7, 0.0], top_k=10)
        for r in results:
            assert -1.0 <= r.score <= 1.0

    def test_query_dimension_mismatch(self):
        """查询向量维度与存储维度不匹配 → score=0.0"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0, 0.0])])

        # 查询向量是 2 维，存储向量是 3 维
        results = store.query([1.0, 0.0], top_k=10)
        assert len(results) == 1
        assert results[0].score == 0.0  # 维度不匹配 → 不相似


# ============================================================
# FakeVectorStore delete 契约测试
# ============================================================

class TestFakeVectorStoreDeleteContract:
    """验证 delete 的输入输出契约"""

    def test_delete_existing_records(self):
        """删除存在的记录，返回删除数量"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0]),
            make_record(id="r2", embedding=[0.0, 1.0]),
        ])

        deleted = store.delete(["r1", "r2"])
        assert deleted == 2
        assert store.count == 0

    def test_delete_nonexistent_returns_zero(self):
        """删除不存在的 id → 返回 0"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        deleted = store.delete(["nonexistent"])
        assert deleted == 0

    def test_delete_partial_match(self):
        """部分 id 存在时只删除存在的"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0])])

        deleted = store.delete(["r1", "r2"])  # r2 不存在
        assert deleted == 1
        assert store.count == 0

    def test_delete_empty_list(self):
        """空列表删除返回 0"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        assert store.delete([]) == 0


# ============================================================
# FakeVectorStore get_by_ids 契约测试
# ============================================================

class TestFakeVectorStoreGetByIdsContract:
    """验证 get_by_ids 的输入输出契约"""

    def test_get_by_ids_returns_dicts(self):
        """get_by_ids 返回 list[dict]"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], text="hello", metadata={"page": 1}),
        ])

        results = store.get_by_ids(["r1"])
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], dict)

    def test_get_by_ids_has_text_and_metadata(self):
        """返回的 dict 包含 id、text、metadata"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], text="hello", metadata={"page": 1, "source": "doc.pdf"}),
        ])

        results = store.get_by_ids(["r1"])
        d = results[0]
        assert d["id"] == "r1"
        assert d["text"] == "hello"
        assert d["metadata"] == {"page": 1, "source": "doc.pdf"}

    def test_get_by_ids_no_embedding(self):
        """返回的 dict 不包含 embedding 字段"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0])])

        results = store.get_by_ids(["r1"])
        assert "embedding" not in results[0]

    def test_get_by_ids_nonexistent(self):
        """不存在的 id 不在结果中"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        results = store.get_by_ids(["nonexistent"])
        assert results == []

    def test_get_by_ids_partial(self):
        """部分 id 存在时只返回存在的"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0])])

        results = store.get_by_ids(["r1", "r2"])
        assert len(results) == 1
        assert results[0]["id"] == "r1"


# ============================================================
# FakeVectorStore delete_by_metadata 契约测试
# ============================================================

class TestFakeVectorStoreDeleteByMetadataContract:
    """验证 delete_by_metadata 的输入输出契约"""

    def test_delete_by_metadata_returns_count(self):
        """按 metadata 删除，返回删除数量"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0, 0.0], metadata={"source": "a.pdf"}),
            make_record(id="r2", embedding=[0.0, 1.0], metadata={"source": "a.pdf"}),
            make_record(id="r3", embedding=[1.0, 1.0], metadata={"source": "b.pdf"}),
        ])

        deleted = store.delete_by_metadata({"source": "a.pdf"})
        assert deleted == 2
        assert store.count == 1  # 只剩 r3

    def test_delete_by_metadata_no_match(self):
        """没有匹配的记录 → 返回 0"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0], metadata={"source": "a.pdf"})])

        deleted = store.delete_by_metadata({"source": "nonexistent.pdf"})
        assert deleted == 0

    def test_delete_by_metadata_multiple_conditions(self):
        """多条件 AND 逻辑"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([
            make_record(id="r1", embedding=[1.0], metadata={"source": "a.pdf", "page": 1}),
            make_record(id="r2", embedding=[1.0], metadata={"source": "a.pdf", "page": 2}),
        ])

        deleted = store.delete_by_metadata({"source": "a.pdf", "page": 1})
        assert deleted == 1
        assert store.count == 1


# ============================================================
# VectorStoreFactory 路由测试
# ============================================================

class TestVectorStoreFactoryRouting:
    """验证 VectorStoreFactory 的路由逻辑"""

    def test_create_fake_store(self):
        """backend='fake' → FakeVectorStore"""
        settings = VectorStoreSettings(backend="fake")
        store = VectorStoreFactory.create(settings)
        assert isinstance(store, FakeVectorStore)

    def test_create_fake_store_works(self):
        """通过工厂创建的 FakeVectorStore 可以正常 upsert+query"""
        settings = VectorStoreSettings(backend="fake")
        store = VectorStoreFactory.create(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0, 0.0])])
        results = store.query([1.0, 0.0, 0.0], top_k=10)
        assert len(results) == 1

    def test_unsupported_backend_raises_error(self):
        """不支持的 backend → VectorStoreError"""
        settings = VectorStoreSettings(backend="nonexistent")
        with pytest.raises(VectorStoreError, match="不支持的 VectorStore backend"):
            VectorStoreFactory.create(settings)

    def test_case_insensitive_backend(self):
        """backend 名称大小写无关"""
        for name in ["fake", "Fake", "FAKE"]:
            settings = VectorStoreSettings(backend=name)
            store = VectorStoreFactory.create(settings)
            assert isinstance(store, FakeVectorStore)

    def test_backend_with_whitespace(self):
        """backend 名称前后空格不影响路由"""
        settings = VectorStoreSettings(backend="  fake  ")
        store = VectorStoreFactory.create(settings)
        assert isinstance(store, FakeVectorStore)

    def test_empty_backend_raises_error(self):
        """backend 为空字符串 → VectorStoreError"""
        settings = VectorStoreSettings(backend="")
        with pytest.raises(VectorStoreError, match="不支持的 VectorStore backend"):
            VectorStoreFactory.create(settings)


# ============================================================
# VectorStoreFactory 注册扩展测试
# ============================================================

class TestVectorStoreFactoryRegister:
    """验证 VectorStoreFactory.register() 的开放-封闭原则"""

    def test_register_custom_backend(self):
        """注册自定义 backend 后可以通过工厂创建"""

        class CustomStore(BaseVectorStore):
            def __init__(self, settings: VectorStoreSettings) -> None:
                self._store: dict = {}
            def upsert(self, records): pass
            def query(self, vector, top_k=10, filters=None): return []
            def delete(self, ids): return 0
            def get_by_ids(self, ids): return []
            def delete_by_metadata(self, filter): return 0

        VectorStoreFactory.register("custom", CustomStore)

        try:
            settings = VectorStoreSettings(backend="custom")
            store = VectorStoreFactory.create(settings)
            assert isinstance(store, CustomStore)
        finally:
            VectorStoreFactory._BACKENDS.pop("custom", None)

    def test_register_non_base_store_raises_error(self):
        """注册非 BaseVectorStore 子类 → VectorStoreError"""

        class NotAStore:
            pass

        with pytest.raises(VectorStoreError, match="不是 BaseVectorStore 的子类"):
            VectorStoreFactory.register("bad", NotAStore)  # type: ignore

    def test_register_overwrite_existing(self):
        """注册同名 backend 会覆盖原有实现"""

        class AnotherFakeStore(BaseVectorStore):
            def __init__(self, settings: VectorStoreSettings) -> None:
                pass
            def upsert(self, records): pass
            def query(self, vector, top_k=10, filters=None): return []
            def delete(self, ids): return 0
            def get_by_ids(self, ids): return []
            def delete_by_metadata(self, filter): return 0

        original = VectorStoreFactory._BACKENDS.get("fake")

        try:
            VectorStoreFactory.register("fake", AnotherFakeStore)
            settings = VectorStoreSettings(backend="fake")
            store = VectorStoreFactory.create(settings)
            assert isinstance(store, AnotherFakeStore)
        finally:
            if original is not None:
                VectorStoreFactory._BACKENDS["fake"] = original


# ============================================================
# Cosine Similarity 计算验证
# ============================================================

class TestCosineSimilarity:
    """验证 FakeVectorStore 的 cosine similarity 计算"""

    def test_identical_vectors(self):
        """相同向量 → score=1.0"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0, 0.0])])
        results = store.query([1.0, 0.0, 0.0], top_k=1)
        assert abs(results[0].score - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        """正交向量 → score=0.0"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0, 0.0])])
        results = store.query([0.0, 1.0, 0.0], top_k=1)
        assert abs(results[0].score - 0.0) < 1e-9

    def test_forty_five_degrees(self):
        """45度角 → score≈0.707"""
        settings = VectorStoreSettings(backend="fake")
        store = FakeVectorStore(settings)
        store.upsert([make_record(id="r1", embedding=[1.0, 0.0])])
        results = store.query([1.0, 1.0], top_k=1)
        expected = 1.0 / math.sqrt(2)
        assert abs(results[0].score - expected) < 1e-9

