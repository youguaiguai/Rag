"""
Ingestion Pipeline 集成测试 — C14: Pipeline 编排

测试策略：
  - 使用 FakeEmbedding + FakeVectorStore 隔离真实 API
  - 使用 tmp_path 隔离文件系统
  - 验收标准：
    1. 对测试文件跑完整 pipeline，成功输出
    2. Pipeline 日志清晰展示各阶段进度
    3. 失败步骤抛出明确异常信息
    4. 增量摄取：未变更文件跳过

测试分类（10 个）：
  - 基础摄取流程（3）
  - 增量摄取（2）
  - 进度回调（2）
  - 批量摄取（1）
  - 错误处理（2）
"""

from __future__ import annotations

import pytest
from core.settings import Settings, VectorStoreSettings
from core.trace.trace_context import TraceContext
from ingestion.pipeline import IngestionPipeline, IngestionResult, PipelineError
from libs.embedding.base_embedding import BaseEmbedding
from libs.vector_store.base_vector_store import BaseVectorStore, VectorRecord, QueryResult
from libs.vector_store.vector_store_factory import FakeVectorStore
from pathlib import Path
from typing import Any


# ============================================================
# MockEmbedding
# ============================================================

class MockEmbedding(BaseEmbedding):
    """Mock Embedding for pipeline testing"""

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

def _make_settings(tmp_path: Path) -> Settings:
    """创建测试用 Settings（使用 fake provider）"""
    s = Settings()
    s.embedding.provider = "fake"
    s.embedding.dimensions = 32
    s.vector_store.backend = "fake"
    s.vector_store.persist_path = str(tmp_path / "chroma")
    s.splitter.provider = "recursive"
    s.splitter.chunk_size = 200
    s.splitter.chunk_overlap = 50
    s.llm.use_llm = False  # 禁用 LLM（规则模式）
    s.vision_llm.enabled = False  # 禁用 Vision LLM
    return s


def _make_markdown_file(tmp_path: Path, name: str = "test_doc.md", content: str = "") -> str:
    """创建测试用 Markdown 文件"""
    if not content:
        content = """# 测试文档

## 第一章 概述

这是一个测试文档，用于验证 Pipeline 的完整摄取流程。

## 第二章 技术架构

系统采用 RAG 架构，包含摄取链路和检索链路。

摄取链路：Loader → Splitter → Transform → Encoder → Storage。

## 第三章 总结

本文档用于测试 Pipeline 编排功能。
"""
    file_path = tmp_path / name
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def _make_pipeline(tmp_path: Path) -> IngestionPipeline:
    """创建测试用 Pipeline（注入 mock 组件）"""
    settings = _make_settings(tmp_path)
    pipeline = IngestionPipeline(settings)

    # 注入 mock embedding
    from ingestion.embedding.dense_encoder import DenseEncoder
    mock_emb = MockEmbedding(dimensions=32)
    pipeline._dense_encoder = DenseEncoder(settings, embedding=mock_emb)
    pipeline._batch_processor._dense_encoder = pipeline._dense_encoder

    # 注入 fake vector store
    from ingestion.storage.vector_upserter import VectorUpserter
    fake_store = FakeVectorStore(VectorStoreSettings())
    pipeline._vector_upserter = VectorUpserter(settings, vector_store=fake_store)

    # BM25 索引器使用临时目录
    pipeline._bm25_indexer._persist_dir = tmp_path / "bm25"
    pipeline._bm25_indexer._index_path = pipeline._bm25_indexer._persist_dir / "bm25_index.json"

    # 文件完整性检查器使用临时目录
    pipeline._integrity._db_path = Path(str(tmp_path / "file_hashes.json"))

    return pipeline


# ============================================================
# 基础摄取流程（3 个）
# ============================================================

class TestBasicIngestion:

    def test_ingest_markdown_success(self, tmp_path):
        """对 Markdown 文件跑完整 pipeline → 成功"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        result = pipeline.ingest(file_path)

        assert result.status == "success"
        assert result.chunks > 0
        assert result.dense_records > 0
        assert result.sparse_vectors > 0
        assert result.duration_ms > 0

    def test_ingest_returns_correct_result_structure(self, tmp_path):
        """返回结果结构正确"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        result = pipeline.ingest(file_path)

        assert isinstance(result, IngestionResult)
        assert result.file_path == file_path
        assert result.doc_id  # 非空
        assert result.chunks > 0
        assert result.dense_records == result.chunks  # dense 数量 = chunk 数量
        assert result.sparse_vectors == result.chunks

    def test_ingest_with_trace(self, tmp_path):
        """带 trace 的摄取 → trace 记录各阶段"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)
        trace = TraceContext(trace_id="test-pipeline")

        pipeline.ingest(file_path, trace=trace)

        # 验证 trace 记录了各阶段
        all_stages = trace.stages
        stage_names = [s.stage for s in all_stages]
        assert any("load" in s for s in stage_names)
        assert any("split" in s for s in stage_names)
        assert any("encode" in s for s in stage_names)


# ============================================================
# 增量摄取（2 个）
# ============================================================

class TestIncrementalIngestion:

    def test_unchanged_file_skipped(self, tmp_path):
        """未变更文件 → 跳过"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        # 第一次摄取
        result1 = pipeline.ingest(file_path)
        assert result1.status == "success"

        # 第二次摄取（未变更 → 跳过）
        result2 = pipeline.ingest(file_path)
        assert result2.status == "skipped"

    def test_force_reingests_unchanged_file(self, tmp_path):
        """force=True → 强制重新摄取"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        # 第一次摄取
        result1 = pipeline.ingest(file_path)
        assert result1.status == "success"

        # 强制重新摄取
        result2 = pipeline.ingest(file_path, force=True)
        assert result2.status == "success"
        assert result2.chunks > 0


# ============================================================
# 进度回调（2 个）
# ============================================================

class TestProgressCallback:

    def test_progress_callback_called(self, tmp_path):
        """进度回调被调用"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        stages_seen: list[str] = []
        pipeline.on_progress(lambda stage, data: stages_seen.append(stage))

        pipeline.ingest(file_path)

        assert len(stages_seen) > 0
        assert "integrity_check" in stages_seen
        assert "load" in stages_seen
        assert "split" in stages_seen
        assert "transform" in stages_seen
        assert "encode" in stages_seen
        assert "store" in stages_seen

    def test_progress_callback_data(self, tmp_path):
        """进度回调包含阶段数据"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        progress_data: list[tuple[str, dict]] = []
        pipeline.on_progress(lambda stage, data: progress_data.append((stage, data)))

        pipeline.ingest(file_path)

        # 验证 split_done 阶段数据
        split_done = [d for s, d in progress_data if s == "split_done"]
        assert len(split_done) == 1
        assert "chunks" in split_done[0]
        assert split_done[0]["chunks"] > 0


# ============================================================
# 批量摄取（1 个）
# ============================================================

class TestBatchIngestion:

    def test_batch_ingest_multiple_files(self, tmp_path):
        """批量摄取多个文件"""
        pipeline = _make_pipeline(tmp_path)

        files = [
            _make_markdown_file(tmp_path, f"doc_{i}.md", f"# 文档 {i}\n\n内容 {i}。")
            for i in range(3)
        ]

        results = pipeline.ingest_batch(files)

        assert len(results) == 3
        for r in results:
            assert r.status == "success"
            assert r.chunks > 0

    def test_batch_ingest_isolates_failures(self, tmp_path):
        """批量摄取中单文件失败不影响其他"""
        pipeline = _make_pipeline(tmp_path)

        valid_file = _make_markdown_file(tmp_path, "valid.md")
        nonexistent_file = str(tmp_path / "nonexistent.md")

        results = pipeline.ingest_batch([valid_file, nonexistent_file])

        assert len(results) == 2
        # 第一个文件成功
        assert results[0].status == "success"
        # 第二个文件失败
        assert results[1].status == "failed"


# ============================================================
# 错误处理（2 个）
# ============================================================

class TestErrorHandling:

    def test_nonexistent_file_raises(self, tmp_path):
        """不存在的文件 → PipelineError"""
        pipeline = _make_pipeline(tmp_path)

        with pytest.raises(PipelineError, match="摄取失败"):
            pipeline.ingest("/nonexistent/file.md")

    def test_failed_result_has_error_message(self, tmp_path):
        """失败结果包含错误信息"""
        pipeline = _make_pipeline(tmp_path)

        try:
            pipeline.ingest("/nonexistent/file.md")
        except PipelineError:
            pass

        # 通过 batch 测试失败结果
        results = pipeline.ingest_batch(["/nonexistent/file.md"])
        assert results[0].status == "failed"
        assert results[0].error  # 非空错误信息

