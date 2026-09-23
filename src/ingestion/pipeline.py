"""
Pipeline 主流程编排 — 串行执行摄取链路

知识点：Pipeline 模式
  - 串行执行多个处理阶段：integrity → load → split → transform → encode → store
  - 每个阶段接收上一阶段输出，传递给下一阶段
  - 失败步骤抛出明确异常（Fail-Fast），Transform 阶段内部降级（Fail-Safe）

Pipeline 流程（面试考点）：
  1. Integrity: FileIntegrityChecker.has_changed(path) → 跳过未变更文件
  2. Load: LoaderFactory.create_for_file(path).load(path) → Document
  3. Split: DocumentChunker.split_document(document) → list[Chunk]
  4. Transform: ChunkRefiner → MetadataEnricher → ImageCaptioner → list[Chunk]
  5. Encode: BatchProcessor.process(chunks) → (list[ChunkRecord], list[SparseVector])
  6. Store: VectorUpserter.upsert(dense) + BM25Indexer.upsert(sparse) → 持久化

接口签名：
  IngestionPipeline(settings: Settings)
  ingest(file_path: str, force: bool = False) -> IngestionResult
  ingest_batch(file_paths: list[str], force: bool = False) -> list[IngestionResult]
"""

from __future__ import annotations

import logging
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord, Document
from dataclasses import dataclass, field
from ingestion.chunking.document_chunker import DocumentChunker
from ingestion.embedding.batch_processor import BatchProcessor
from ingestion.embedding.dense_encoder import DenseEncoder
from ingestion.embedding.sparse_encoder import SparseEncoder, SparseVector
from ingestion.storage.bm25_indexer import BM25Indexer
from ingestion.storage.vector_upserter import VectorUpserter
from ingestion.transform.chunk_refiner import ChunkRefiner
from ingestion.transform.image_captioner import ImageCaptioner
from ingestion.transform.metadata_enricher import MetadataEnricher
from libs.loader.base_loader import LoaderError
from libs.loader.file_integrity import FileIntegrityChecker
from libs.loader.loader_factory import LoaderFactory
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from core.settings import Settings

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构：IngestionResult — 单文件摄取结果
# ============================================================

@dataclass
class IngestionResult:
    """单文件摄取结果

    接口签名：IngestionResult(file_path, status, doc_id, chunks, dense_records, sparse_vectors, duration_ms, error)
    字段说明：
      - file_path: 源文件路径
      - status: "success" | "skipped" | "failed"
      - doc_id: 文档 ID（status=skipped 时可能为空）
      - chunks: chunk 数量
      - dense_records: dense 编码记录数
      - sparse_vectors: sparse 编码向量数
      - duration_ms: 总耗时（毫秒）
      - error: 失败原因（status=failed 时）
    """
    file_path: str
    status: str  # "success" | "skipped" | "failed"
    doc_id: str = ""
    chunks: int = 0
    dense_records: int = 0
    sparse_vectors: int = 0
    duration_ms: float = 0.0
    error: str = ""
    stages: dict[str, Any] = field(default_factory=dict)


class PipelineError(Exception):
    """Pipeline 异常

    知识点：Pipeline 的异常策略
      - 配置错误、文件不存在 → PipelineError（Fail-Fast）
      - Transform 内部失败 → 降级（Fail-Safe，不阻塞）
      - Encode/Store 失败 → PipelineError（无法降级）
    """
    pass


# ============================================================
# IngestionPipeline — 主流程编排
# ============================================================

class IngestionPipeline:
    """摄取管线 — 串行执行 integrity → load → split → transform → encode → store

    知识点：Pipeline 模式的三个设计原则
      1. 单向数据流：每个阶段只接收上一阶段输出，不回退
      2. 阶段隔离：单个阶段失败不影响其他阶段的代码（异常隔离）
      3. 可观测性：每个阶段记录 trace，便于调试和性能分析

    接口签名：
      IngestionPipeline(settings: Settings)
      ingest(file_path: str, force: bool = False) -> IngestionResult
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 Pipeline — 创建各阶段组件

        接口签名：IngestionPipeline(settings: Settings)
        入参：settings — 全局配置
        """
        self._settings = settings

        # 各阶段组件（延迟创建重型资源）
        self._integrity = FileIntegrityChecker(
            db_path=settings.observability.db_path.replace("file_hashes.json", "file_hashes.json")
            if hasattr(settings, "observability") and hasattr(settings.observability, "db_path")
            else "data/db/file_hashes.json"
        )
        self._chunker = DocumentChunker(settings)

        # Transform 链
        self._chunk_refiner = ChunkRefiner(settings)
        self._metadata_enricher = MetadataEnricher(settings)
        self._image_captioner = ImageCaptioner(settings)

        # 编码器
        self._dense_encoder = DenseEncoder(settings)
        self._sparse_encoder = SparseEncoder(settings)
        self._batch_processor = BatchProcessor(
            settings,
            dense_encoder=self._dense_encoder,
            sparse_encoder=self._sparse_encoder,
        )

        # 存储层
        self._vector_upserter = VectorUpserter(settings)
        self._bm25_indexer = BM25Indexer(
            persist_path="data/db/bm25",
        )

        # 进度回调
        self._on_progress: Callable[[str, dict], None] | None = None

    # --------------------------------------------------------
    # 主入口：ingest
    # --------------------------------------------------------

    def ingest(
        self,
        file_path: str,
        force: bool = False,
        trace: TraceContext | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> IngestionResult:
        """摄取单个文件

        接口签名：ingest(file_path, force=False, trace=None, on_progress=None) -> IngestionResult
        入参：
          - file_path: 文件路径
          - force: 是否强制重新摄取
          - trace: 可选追踪上下文
          - on_progress: 可选进度回调 (stage_name, current, total)
        出参：IngestionResult

        F5 on_progress 回调：
          - stage_name: 当前阶段名称（load/split/transform/embed/upsert）
          - current: 当前阶段索引（1-based）
          - total: 总阶段数
          - on_progress=None 时完全不影响现有行为
        """
        import time

        start_time = time.monotonic()
        result = IngestionResult(file_path=file_path, status="success")

        # F5: 定义阶段列表（用于计算进度）
        _stages = ["load", "split", "transform", "embed", "upsert"]
        _total_stages = len(_stages)
        def _report_progress(stage_name: str, idx: int) -> None:
            if on_progress is not None:
                try:
                    on_progress(stage_name, idx, _total_stages)
                except Exception as e:
                    logger.warning("Pipeline: on_progress 回调异常: %s", e)

        try:
            # 1. Integrity check
            self._emit_progress("integrity_check", {"file_path": file_path, "force": force})
            if not force and not self._integrity.has_changed(file_path):
                result.status = "skipped"
                result.duration_ms = round((time.monotonic() - start_time) * 1000, 2)
                logger.info("Pipeline: 跳过未变更文件 %s", file_path)
                return result

            # 2. Load
            _report_progress("load", 1)
            self._emit_progress("load", {"file_path": file_path})
            document = self._load(file_path, trace)
            result.doc_id = document.doc_id
            self._emit_progress("load_done", {"doc_id": document.doc_id, "text_length": len(document.text)})

            # 3. Split
            _report_progress("split", 2)
            self._emit_progress("split", {"doc_id": document.doc_id})
            chunks = self._split(document, trace)
            result.chunks = len(chunks)
            self._emit_progress("split_done", {"chunks": len(chunks)})

            # 4. Transform chain
            _report_progress("transform", 3)
            self._emit_progress("transform", {"chunks": len(chunks)})
            chunks = self._transform(chunks, trace)
            self._emit_progress("transform_done", {"chunks": len(chunks)})

            # 5. Encode
            _report_progress("embed", 4)
            self._emit_progress("encode", {"chunks": len(chunks)})
            dense_records, sparse_vectors = self._encode(chunks, trace)
            result.dense_records = len(dense_records)
            result.sparse_vectors = len(sparse_vectors)
            self._emit_progress("encode_done", {
                "dense": len(dense_records),
                "sparse": len(sparse_vectors),
            })

            # 6. Store
            _report_progress("upsert", 5)
            self._emit_progress("store", {
                "dense": len(dense_records),
                "sparse": len(sparse_vectors),
            })
            self._store(dense_records, sparse_vectors, trace)
            self._emit_progress("store_done", {})

            # 7. Update hash
            self._integrity.update_hash(file_path)
            self._integrity.save()

            result.duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            logger.info(
                "Pipeline: %s 摄取完成，%d chunks → %d dense + %d sparse (%.0fms)",
                file_path, result.chunks, result.dense_records, result.sparse_vectors,
                result.duration_ms,
            )

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            result.duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            logger.error("Pipeline: %s 摄取失败: %s", file_path, e)
            # 不吞异常，重新抛出让调用方处理
            raise PipelineError(f"摄取失败 {file_path}: {e}") from e

        return result

    # --------------------------------------------------------
    # 批量摄取
    # --------------------------------------------------------

    def ingest_batch(
        self,
        file_paths: list[str],
        force: bool = False,
    ) -> list[IngestionResult]:
        """批量摄取多个文件

        接口签名：ingest_batch(file_paths, force=False) -> list[IngestionResult]
        出参：每个文件的摄取结果

        知识点：批量摄取的异常隔离
          - 单个文件失败不影响其他文件
          - 失败的文件标记 status="failed"
          - 面试考点："批量摄取怎么处理失败？" → 隔离 + 记录 + 继续
        """
        results: list[IngestionResult] = []
        for path in file_paths:
            try:
                result = self.ingest(path, force=force)
                results.append(result)
            except PipelineError as e:
                # 单文件失败不阻塞其他文件
                results.append(IngestionResult(
                    file_path=path,
                    status="failed",
                    error=str(e),
                ))
                logger.warning("Pipeline: 批量摄取中 %s 失败，继续处理下一个", path)
        return results

    # --------------------------------------------------------
    # 各阶段实现
    # --------------------------------------------------------

    def _load(self, file_path: str, trace: TraceContext | None) -> Document:
        """阶段 2: 加载文件"""
        import time
        start = time.monotonic()

        loader = LoaderFactory.create_for_file(file_path)
        document = loader.load(file_path)

        if trace:
            trace.record_stage("load", {
                "method": type(loader).__name__,
                "file_path": file_path,
                "doc_id": document.doc_id,
                "text_length": len(document.text),
            }, duration_ms=round((time.monotonic() - start) * 1000, 2))

        return document

    def _split(self, document: Document, trace: TraceContext | None) -> list[Chunk]:
        """阶段 3: 切分文档"""
        import time
        start = time.monotonic()

        chunks = self._chunker.split_document(document)

        if trace:
            trace.record_stage("split", {
                "method": type(self._chunker).__name__,
                "doc_id": document.doc_id,
                "chunks": len(chunks),
            }, duration_ms=round((time.monotonic() - start) * 1000, 2))

        return chunks

    def _transform(self, chunks: list[Chunk], trace: TraceContext | None) -> list[Chunk]:
        """阶段 4: Transform 链（ChunkRefiner → MetadataEnricher → ImageCaptioner）

        知识点：Transform 链的执行顺序
          1. ChunkRefiner: 先去噪 → 干净文本有利于后续阶段
          2. MetadataEnricher: 补元数据 → title/summary/tags
          3. ImageCaptioner: 最后处理图片 → 需要 Vision LLM
          - 面试考点："为什么这个顺序？" → 去噪优先 + 元数据次之 + 图片最后（最可能降级）
        """
        import time
        start = time.monotonic()

        # 4a. ChunkRefiner
        chunks = self._chunk_refiner.transform(chunks, trace=trace)

        # 4b. MetadataEnricher
        chunks = self._metadata_enricher.transform(chunks, trace=trace)

        # 4c. ImageCaptioner
        chunks = self._image_captioner.transform(chunks, trace=trace)

        if trace:
            trace.record_stage("transform", {
                "method": "TransformChain",
                "refiner": type(self._chunk_refiner).__name__,
                "enricher": type(self._metadata_enricher).__name__,
                "captioner": type(self._image_captioner).__name__,
                "chunks": len(chunks),
            }, duration_ms=round((time.monotonic() - start) * 1000, 2))

        return chunks

    def _encode(
        self,
        chunks: list[Chunk],
        trace: TraceContext | None,
    ) -> tuple[list[ChunkRecord], list[SparseVector]]:
        """阶段 5: 编码（Dense + Sparse）"""
        import time
        start = time.monotonic()

        dense_records, sparse_vectors = self._batch_processor.process(chunks, trace=trace)

        if trace:
            trace.record_stage("embed", {
                "method": type(self._batch_processor).__name__,
                "chunks": len(chunks),
                "dense": len(dense_records),
                "sparse": len(sparse_vectors),
            }, duration_ms=round((time.monotonic() - start) * 1000, 2))

        return dense_records, sparse_vectors

    def _store(
        self,
        dense_records: list[ChunkRecord],
        sparse_vectors: list[SparseVector],
        trace: TraceContext | None,
    ) -> None:
        """阶段 6: 持久化存储

        知识点：存储顺序
          1. VectorUpserter（Dense）→ 向量数据库
          2. BM25Indexer（Sparse）→ 倒排索引
          - 面试考点："为什么 Dense 先存？" → Dense 是主索引，Sparse 是辅助
        """
        import time

        # 6. Store: Dense + Sparse
        start = time.monotonic()
        dense_count = self._vector_upserter.upsert(dense_records, trace=trace)
        self._bm25_indexer.upsert(sparse_vectors, trace=trace)
        if trace:
            trace.record_stage("upsert", {
                "method": type(self._vector_upserter).__name__,
                "dense_count": dense_count,
                "sparse_count": len(sparse_vectors),
            }, duration_ms=round((time.monotonic() - start) * 1000, 2))

    # --------------------------------------------------------
    # 进度回调
    # --------------------------------------------------------

    def on_progress(self, callback: Callable[[str, dict], None]) -> None:
        """注册进度回调函数

        接口签名：on_progress(callback: Callable[[str, dict], None]) -> None
        用途：Dashboard 据此展示进度条

        知识点：回调模式 (Callback Pattern)
          - Pipeline 在每个阶段切换时调用回调
          - 回调可以更新 UI、写日志、发送通知
          - 面试考点："为什么用回调而非事件？" → 简单 + 同步 + 可控
        """
        self._on_progress = callback

    def _emit_progress(self, stage: str, data: dict[str, Any]) -> None:
        """触发进度回调"""
        if self._on_progress is not None:
            try:
                self._on_progress(stage, data)
            except Exception as e:
                logger.warning("Pipeline: 进度回调异常: %s", e)

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def bm25_indexer(self) -> BM25Indexer:
        return self._bm25_indexer

    @property
    def vector_upserter(self) -> VectorUpserter:
        return self._vector_upserter

