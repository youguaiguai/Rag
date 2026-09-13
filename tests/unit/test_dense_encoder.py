"""
DenseEncoder 单元测试 — C8: 稠密向量编码

测试策略：
  - 使用 FakeEmbedding 隔离，不依赖真实 API
  - 验收标准全覆盖：
    1. 输出向量数量与 chunks 数量一致
    2. 维度一致
    3. 空输入处理
    4. ChunkRecord 字段正确映射
    5. 错误场景：数量不一致、维度不匹配

测试分类（15 个）：
  - 基础 + 空输入（3）
  - 编码正确性（4）
  - 批量处理（2）
  - 属性（2）
  - 错误场景（2）
  - Trace + Settings（2）
"""

from __future__ import annotations

import pytest
from core.settings import Settings, EmbeddingSettings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord
from ingestion.embedding.dense_encoder import DenseEncoder
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from typing import Any


# ============================================================
# MockEmbedding — 可编程测试桩
# ============================================================

class MockEmbedding(BaseEmbedding):
    """可编程 Mock Embedding — 可配置维度/返回值/异常"""

    def __init__(
        self,
        dimensions: int = 128,
        error: Exception | None = None,
        output_count_override: int | None = None,
        output_dim_override: int | None = None,
    ) -> None:
        self._model = "mock-embedding-model"
        self._dims = dimensions
        self._error = error
        self._output_count_override = output_count_override
        self._output_dim_override = output_dim_override
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.calls.append(texts)
        if self._error is not None:
            raise self._error

        count = self._output_count_override if self._output_count_override is not None else len(texts)
        dim = self._output_dim_override if self._output_dim_override is not None else self._dims

        return [[0.01 * (i + 1) for i in range(dim)] for _ in range(count)]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dims


# ============================================================
# 辅助函数
# ============================================================

def _make_settings(provider: str = "fake", dimensions: int = 128) -> Settings:
    s = Settings()
    s.embedding.provider = provider
    s.embedding.dimensions = dimensions
    return s


def _make_chunk(text: str = "测试文本", chunk_id: str = "c_0001",
                index: int = 0, metadata: dict[str, Any] | None = None) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc123",
        text=text,
        index=index,
        source_ref=f"/test.md#chunk={index}",
        metadata=metadata or {"title": "测试"},
    )


# ============================================================
# 基础 + 空输入（3 个）
# ============================================================

class TestBasicAndEmpty:

    def test_empty_list_returns_empty(self):
        """空列表 → 空列表（不调用 API）"""
        mock_emb = MockEmbedding()
        encoder = DenseEncoder(_make_settings(), embedding=mock_emb)
        result = encoder.encode([])

        assert result == []
        assert len(mock_emb.calls) == 0

    def test_empty_list_with_trace(self):
        """空列表 + trace → 记录 total=0"""
        mock_emb = MockEmbedding()
        encoder = DenseEncoder(_make_settings(), embedding=mock_emb)
        trace = TraceContext(trace_id="test-encoder")
        encoder.encode([], trace=trace)

        stages = trace.get_stages("dense_encoder")
        assert len(stages) == 1
        assert stages[0].data["total"] == 0

    def test_single_chunk(self):
        """单个 chunk → 单个 ChunkRecord"""
        mock_emb = MockEmbedding(dimensions=64)
        encoder = DenseEncoder(_make_settings(dimensions=64), embedding=mock_emb)
        chunk = _make_chunk("一段文本")
        result = encoder.encode([chunk])

        assert len(result) == 1
        assert isinstance(result[0], ChunkRecord)
        assert len(result[0].embedding) == 64


# ============================================================
# 编码正确性（4 个）
# ============================================================

class TestEncodingCorrectness:

    def test_output_count_matches_input(self):
        """输出向量数量与 chunks 数量一致"""
        mock_emb = MockEmbedding(dimensions=32)
        encoder = DenseEncoder(_make_settings(dimensions=32), embedding=mock_emb)
        chunks = [_make_chunk(f"文本{i}", chunk_id=f"c_{i:04d}", index=i) for i in range(5)]
        result = encoder.encode(chunks)

        assert len(result) == 5

    def test_dimensions_consistent(self):
        """所有向量维度一致"""
        mock_emb = MockEmbedding(dimensions=256)
        encoder = DenseEncoder(_make_settings(dimensions=256), embedding=mock_emb)
        chunks = [_make_chunk(f"文本{i}", chunk_id=f"c_{i:04d}", index=i) for i in range(3)]
        result = encoder.encode(chunks)

        for record in result:
            assert len(record.embedding) == 256

    def test_chunk_fields_mapped_to_record(self):
        """Chunk 字段正确映射到 ChunkRecord"""
        mock_emb = MockEmbedding(dimensions=16)
        encoder = DenseEncoder(_make_settings(dimensions=16), embedding=mock_emb)
        chunk = _make_chunk("映射测试", chunk_id="c_map", index=3,
                            metadata={"title": "标题", "tags": ["a", "b"]})
        result = encoder.encode([chunk])

        record = result[0]
        assert record.chunk_id == "c_map"
        assert record.doc_id == "doc123"
        assert record.text == "映射测试"
        assert record.metadata["title"] == "标题"
        assert record.source_ref == "/test.md#chunk=3"
        assert len(record.embedding) == 16

    def test_batch_embed_called_once(self):
        """批量编码：所有文本一次性送入 embed"""
        mock_emb = MockEmbedding(dimensions=16)
        encoder = DenseEncoder(_make_settings(dimensions=16), embedding=mock_emb)
        chunks = [_make_chunk(f"文本{i}", chunk_id=f"c_{i:04d}", index=i) for i in range(5)]
        encoder.encode(chunks)

        assert len(mock_emb.calls) == 1
        assert len(mock_emb.calls[0]) == 5


# ============================================================
# 批量处理（2 个）
# ============================================================

class TestBatchProcessing:

    def test_large_batch(self):
        """大批量 chunks（20 个）"""
        mock_emb = MockEmbedding(dimensions=32)
        encoder = DenseEncoder(_make_settings(dimensions=32), embedding=mock_emb)
        chunks = [_make_chunk(f"批量文本{i}", chunk_id=f"b_{i:04d}", index=i) for i in range(20)]
        result = encoder.encode(chunks)

        assert len(result) == 20
        for i, record in enumerate(result):
            assert record.chunk_id == f"b_{i:04d}"

    def test_texts_extracted_in_order(self):
        """文本按顺序提取"""
        mock_emb = MockEmbedding(dimensions=8)
        encoder = DenseEncoder(_make_settings(dimensions=8), embedding=mock_emb)
        chunks = [
            _make_chunk("第一个", chunk_id="c_0", index=0),
            _make_chunk("第二个", chunk_id="c_1", index=1),
            _make_chunk("第三个", chunk_id="c_2", index=2),
        ]
        encoder.encode(chunks)

        assert mock_emb.calls[0] == ["第一个", "第二个", "第三个"]


# ============================================================
# 属性（2 个）
# ============================================================

class TestProperties:

    def test_dimensions_property(self):
        """dimensions 属性返回正确值"""
        mock_emb = MockEmbedding(dimensions=512)
        encoder = DenseEncoder(_make_settings(dimensions=512), embedding=mock_emb)
        assert encoder.dimensions == 512

    def test_model_name_property(self):
        """model_name 属性返回正确值"""
        mock_emb = MockEmbedding()
        encoder = DenseEncoder(_make_settings(), embedding=mock_emb)
        assert encoder.model_name == "mock-embedding-model"


# ============================================================
# 错误场景（2 个）
# ============================================================

class TestErrorScenarios:

    def test_count_mismatch_raises(self):
        """向量数量不一致 → 抛 EmbeddingError"""
        mock_emb = MockEmbedding(dimensions=16, output_count_override=3)
        encoder = DenseEncoder(_make_settings(dimensions=16), embedding=mock_emb)

        chunks = [_make_chunk(f"t{i}", chunk_id=f"c_{i}", index=i) for i in range(5)]
        with pytest.raises(EmbeddingError, match="编码数量不一致"):
            encoder.encode(chunks)

    def test_dimension_mismatch_raises(self):
        """维度不匹配 → 抛 EmbeddingError"""
        mock_emb = MockEmbedding(dimensions=16, output_dim_override=32)
        encoder = DenseEncoder(_make_settings(dimensions=16), embedding=mock_emb)

        chunk = _make_chunk("维度测试")
        with pytest.raises(EmbeddingError, match="维度不匹配"):
            encoder.encode([chunk])


# ============================================================
# Trace + Settings（2 个）
# ============================================================

class TestTraceAndSettings:

    def test_trace_records_stage(self):
        """trace 上下文记录阶段数据"""
        mock_emb = MockEmbedding(dimensions=64)
        encoder = DenseEncoder(_make_settings(dimensions=64), embedding=mock_emb)
        trace = TraceContext(trace_id="test-encoder")

        chunks = [_make_chunk("a", chunk_id="c_0", index=0),
                  _make_chunk("b", chunk_id="c_1", index=1)]
        encoder.encode(chunks, trace=trace)

        stages = trace.get_stages("dense_encoder")
        assert len(stages) == 1
        assert stages[0].data["total"] == 2
        assert stages[0].data["dims"] == 64
        assert stages[0].data["model"] == "mock-embedding-model"

    def test_factory_creates_embedding_when_not_injected(self):
        """未注入 embedding 时从工厂创建（FakeEmbedding）"""
        settings = _make_settings(provider="fake", dimensions=128)
        encoder = DenseEncoder(settings)
        assert encoder.dimensions == 128
        assert encoder.model_name == "fake-embedding-model"

