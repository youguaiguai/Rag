"""
BatchProcessor 单元测试 — C10: 批处理编排

测试策略：
  - 使用 MockEmbedding + FakeEmbedding 隔离
  - 验收标准全覆盖：
    1. batch_size=2 时 5 chunks → 3 批，顺序稳定
    2. 空输入处理
    3. Dense + Sparse 双编码
    4. 仅 Sparse 编码（无 Dense）
    5. 结果顺序一致性

测试分类（14 个）：
  - 分批逻辑（3）
  - 基础 + 空输入（2）
  - 双编码驱动（3）
  - 仅 Sparse 编码（2）
  - 顺序稳定性（2）
  - Trace + 属性（2）
"""

from __future__ import annotations

import pytest
from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord
from ingestion.embedding.batch_processor import BatchProcessor, BatchResult
from ingestion.embedding.dense_encoder import DenseEncoder
from ingestion.embedding.sparse_encoder import SparseEncoder, SparseVector
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from typing import Any


# ============================================================
# MockEmbedding
# ============================================================

class MockEmbedding(BaseEmbedding):
    """可编程 Mock Embedding"""

    def __init__(self, dimensions: int = 32) -> None:
        self._model = "mock-embedding"
        self._dims = dimensions

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [[0.01 * (i + 1) for i in range(self._dims)] for _ in texts]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dims


# ============================================================
# 辅助函数
# ============================================================

def _make_chunks(n: int, prefix: str = "c") -> list[Chunk]:
    """创建 n 个 chunk"""
    return [
        Chunk(
            chunk_id=f"{prefix}_{i:04d}",
            doc_id="doc123",
            text=f"文本内容 {i}",
            index=i,
            source_ref=f"/test.md#chunk={i}",
            metadata={},
        )
        for i in range(n)
    ]


def _make_settings(batch_size: int = 100) -> Settings:
    s = Settings()
    s.embedding.provider = "fake"
    s.embedding.dimensions = 32
    # 设置 batch_size（通过 ingestion 配置，如果没有该字段则用默认值）
    return s


# ============================================================
# 分批逻辑（3 个）
# ============================================================

class TestBatchSplitting:

    def test_5_chunks_batch_size_2_gives_3_batches(self):
        """验收标准：batch_size=2, 5 chunks → 3 批"""
        settings = _make_settings()
        processor = BatchProcessor(settings, sparse_encoder=SparseEncoder(settings))
        processor._batch_size = 2  # 直接设置

        chunks = _make_chunks(5)
        batches = processor._split_batches(chunks)

        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    def test_exact_multiple_no_remainder(self):
        """batch_size 整除：6 chunks / bs=3 → 2 批"""
        settings = _make_settings()
        processor = BatchProcessor(settings, sparse_encoder=SparseEncoder(settings))
        processor._batch_size = 3

        chunks = _make_chunks(6)
        batches = processor._split_batches(chunks)

        assert len(batches) == 2
        for batch in batches:
            assert len(batch) == 3

    def test_single_batch_when_batch_size_exceeds_count(self):
        """batch_size > chunk 数 → 1 批"""
        settings = _make_settings()
        processor = BatchProcessor(settings, sparse_encoder=SparseEncoder(settings))
        processor._batch_size = 100

        chunks = _make_chunks(5)
        batches = processor._split_batches(chunks)

        assert len(batches) == 1
        assert len(batches[0]) == 5


# ============================================================
# 基础 + 空输入（2 个）
# ============================================================

class TestBasicAndEmpty:

    def test_empty_list_returns_empty(self):
        """空列表 → ([], [])"""
        settings = _make_settings()
        processor = BatchProcessor(settings, sparse_encoder=SparseEncoder(settings))
        dense, sparse = processor.process([])

        assert dense == []
        assert sparse == []

    def test_empty_list_with_trace(self):
        """空列表 + trace → 记录 total=0"""
        settings = _make_settings()
        processor = BatchProcessor(settings, sparse_encoder=SparseEncoder(settings))
        trace = TraceContext(trace_id="test-batch")
        processor.process([], trace=trace)

        stages = trace.get_stages("batch_processor")
        assert len(stages) == 1
        assert stages[0].data["total_chunks"] == 0


# ============================================================
# 双编码驱动（3 个）
# ============================================================

class TestDualEncoding:

    def test_dense_and_sparse_both_encoded(self):
        """Dense + Sparse 双编码"""
        settings = _make_settings()
        mock_emb = MockEmbedding(dimensions=16)
        dense_enc = DenseEncoder(settings, embedding=mock_emb)
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, dense_encoder=dense_enc, sparse_encoder=sparse_enc)
        processor._batch_size = 2

        chunks = _make_chunks(5)
        dense, sparse = processor.process(chunks)

        assert len(dense) == 5
        assert len(sparse) == 5
        for record in dense:
            assert isinstance(record, ChunkRecord)
            assert len(record.embedding) == 16
        for vec in sparse:
            assert isinstance(vec, SparseVector)

    def test_output_count_matches_input(self):
        """输出数量与输入一致"""
        settings = _make_settings()
        mock_emb = MockEmbedding(dimensions=8)
        dense_enc = DenseEncoder(settings, embedding=mock_emb)
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, dense_encoder=dense_enc, sparse_encoder=sparse_enc)
        processor._batch_size = 3

        chunks = _make_chunks(10)
        dense, sparse = processor.process(chunks)

        assert len(dense) == 10
        assert len(sparse) == 10

    def test_multiple_batches_all_collected(self):
        """多批次结果全部收集"""
        settings = _make_settings()
        mock_emb = MockEmbedding(dimensions=8)
        dense_enc = DenseEncoder(settings, embedding=mock_emb)
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, dense_encoder=dense_enc, sparse_encoder=sparse_enc)
        processor._batch_size = 2

        chunks = _make_chunks(7)
        dense, sparse = processor.process(chunks)

        # 7 chunks / bs=2 → 4 batches [2,2,2,1]
        assert len(dense) == 7
        assert len(sparse) == 7


# ============================================================
# 仅 Sparse 编码（2 个）
# ============================================================

class TestSparseOnly:

    def test_sparse_only_no_dense(self):
        """无 Dense 编码器 → 只做 Sparse"""
        settings = _make_settings()
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, dense_encoder=None, sparse_encoder=sparse_enc)
        processor._batch_size = 2

        chunks = _make_chunks(3)
        dense, sparse = processor.process(chunks)

        assert dense == []
        assert len(sparse) == 3

    def test_sparse_only_with_large_batch(self):
        """仅 Sparse + 大批量"""
        settings = _make_settings()
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, dense_encoder=None, sparse_encoder=sparse_enc)
        processor._batch_size = 50

        chunks = _make_chunks(20)
        dense, sparse = processor.process(chunks)

        assert dense == []
        assert len(sparse) == 20


# ============================================================
# 顺序稳定性（2 个）
# ============================================================

class TestOrderStability:

    def test_chunk_ids_in_order(self):
        """验收标准：顺序稳定 — chunk_id 按原始顺序"""
        settings = _make_settings()
        mock_emb = MockEmbedding(dimensions=8)
        dense_enc = DenseEncoder(settings, embedding=mock_emb)
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, dense_encoder=dense_enc, sparse_encoder=sparse_enc)
        processor._batch_size = 2

        chunks = _make_chunks(5)
        dense, sparse = processor.process(chunks)

        # Dense 顺序
        for i, record in enumerate(dense):
            assert record.chunk_id == f"c_{i:04d}"

        # Sparse 顺序
        for i, vec in enumerate(sparse):
            assert vec.chunk_id == f"c_{i:04d}"

    def test_cross_batch_order_continuous(self):
        """跨批次顺序连续"""
        settings = _make_settings()
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, sparse_encoder=sparse_enc)
        processor._batch_size = 3

        chunks = _make_chunks(8)
        _, sparse = processor.process(chunks)

        for i, vec in enumerate(sparse):
            assert vec.chunk_id == f"c_{i:04d}"


# ============================================================
# Trace + 属性（2 个）
# ============================================================

class TestTraceAndProperties:

    def test_trace_records_batch_details(self):
        """trace 记录每批详情"""
        settings = _make_settings()
        mock_emb = MockEmbedding(dimensions=8)
        dense_enc = DenseEncoder(settings, embedding=mock_emb)
        sparse_enc = SparseEncoder(settings)
        processor = BatchProcessor(settings, dense_encoder=dense_enc, sparse_encoder=sparse_enc)
        processor._batch_size = 2

        chunks = _make_chunks(5)
        trace = TraceContext(trace_id="test-batch")
        processor.process(chunks, trace=trace)

        stages = trace.get_stages("batch_processor")
        assert len(stages) == 1
        data = stages[0].data
        assert data["total_chunks"] == 5
        assert data["total_batches"] == 3
        assert data["batch_size"] == 2
        assert len(data["batches"]) == 3
        # 验证每批的 chunk 数量
        assert data["batches"][0]["chunks"] == 2
        assert data["batches"][1]["chunks"] == 2
        assert data["batches"][2]["chunks"] == 1
        # 每批都有耗时
        for batch_info in data["batches"]:
            assert "duration_ms" in batch_info

    def test_batch_size_property(self):
        """batch_size 属性"""
        settings = _make_settings()
        processor = BatchProcessor(settings, sparse_encoder=SparseEncoder(settings))
        assert processor.batch_size == 100  # 默认值

