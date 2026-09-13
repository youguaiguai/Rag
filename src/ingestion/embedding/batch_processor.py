"""
BatchProcessor — 批处理编排器（分 batch 驱动 Dense + Sparse 编码）

知识点：BatchProcessor 在 RAG Pipeline 中的位置
  - 摄取链路：... → Transform 链 → **BatchProcessor** → Storage
  - 职责：将 chunks 分 batch，逐批驱动 DenseEncoder + SparseEncoder，合并结果
  - 设计原因：Embedding API 有批量大小限制（如 OpenAI 单次最多 2048 个输入）
  - 面试考点："为什么要分 batch？" → API 限制 + 内存控制 + 错误隔离

分批策略：
  - 按顺序切分（保持 chunk 顺序稳定）
  - batch_size 控制每批大小
  - 最后一批可能不满（如 5 chunks / batch_size=2 → [2, 2, 1]）
  - 空列表 → 空列表输出

编码驱动：
  - DenseEncoder.encode(batch) → list[ChunkRecord]
  - SparseEncoder.encode(batch) → list[SparseVector]
  - 两个编码器独立运行，结果按 chunk_id 对齐合并
  - 可选只运行 dense 或只运行 sparse

接口签名：
  BatchProcessor(settings: Settings, dense_encoder: DenseEncoder | None = None, sparse_encoder: SparseEncoder | None = None)
  process(chunks: list[Chunk], trace: TraceContext | None = None) -> tuple[list[ChunkRecord], list[SparseVector]]
"""

from __future__ import annotations

import logging
import time
from core.types import Chunk, ChunkRecord
from dataclasses import dataclass, field
from ingestion.embedding.dense_encoder import DenseEncoder
from ingestion.embedding.sparse_encoder import SparseEncoder, SparseVector
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构：BatchResult — 单批处理结果
# ============================================================

@dataclass
class BatchResult:
    """单批处理结果（用于 trace 记录）

    接口签名：BatchResult(batch_index, chunk_count, dense_count, sparse_count, duration_ms)
    字段说明：
      - batch_index: 批次序号（0-based）
      - chunk_count: 该批 chunk 数量
      - dense_count: Dense 编码输出数量
      - sparse_count: Sparse 编码输出数量
      - duration_ms: 该批处理耗时（毫秒）
    """
    batch_index: int
    chunk_count: int
    dense_count: int
    sparse_count: int
    duration_ms: float


# ============================================================
# BatchProcessor — 批处理编排器
# ============================================================

class BatchProcessor:
    """批处理编排器 — 分 batch 驱动 Dense + Sparse 编码

    知识点：批处理设计的三个考量
      1. 批量大小（batch_size）：平衡 API 利用率和内存/超时限制
      2. 顺序稳定性：同一批内保持 chunk 顺序，跨批保持批次顺序
      3. 错误隔离：单批失败不影响其他批（当前实现：整体抛异常，后续可改为降级）

    接口签名：
      BatchProcessor(settings, dense_encoder=None, sparse_encoder=None)
      process(chunks, trace=None) -> tuple[list[ChunkRecord], list[SparseVector]]
    """

    def __init__(
        self,
        settings: Settings,
        dense_encoder: DenseEncoder | None = None,
        sparse_encoder: SparseEncoder | None = None,
    ) -> None:
        """初始化 BatchProcessor

        接口签名：BatchProcessor(settings, dense_encoder=None, sparse_encoder=None)
        入参：
          - settings: 全局配置
          - dense_encoder: 可选的 DenseEncoder 实例（注入优先；未注入时自动创建）
          - sparse_encoder: 可选的 SparseEncoder 实例（注入优先；未注入时自动创建）
        """
        self._settings = settings

        # batch_size 从 settings 读取（或默认值）
        # 知识点：batch_size 的选择
        #   - OpenAI Embedding API 单次最多 2048 个输入
        #   - 实际推荐 100-500（平衡延迟和吞吐）
        #   - 面试考点："batch_size 怎么选？" → 看API限制 + 网络条件 + 内存
        self._batch_size: int = 100
        if hasattr(settings, "ingestion") and hasattr(settings.ingestion, "batch_size"):
            self._batch_size = max(1, settings.ingestion.batch_size)  # type: ignore[attr-defined]

        # 编码器：注入优先；未注入时自动创建
        self._dense_encoder: DenseEncoder | None = dense_encoder
        self._sparse_encoder: SparseEncoder = sparse_encoder or SparseEncoder(settings)

    # --------------------------------------------------------
    # 主入口：process
    # --------------------------------------------------------

    def process(
        self,
        chunks: list[Chunk],
        trace: TraceContext | None = None,
    ) -> tuple[list[ChunkRecord], list[SparseVector]]:
        """对 chunks 分批执行 Dense + Sparse 编码

        接口签名：process(chunks, trace=None) -> tuple[list[ChunkRecord], list[SparseVector]]
        入参：
          - chunks: 待编码的 Chunk 列表
          - trace: 可选追踪上下文
        出参：(dense_records, sparse_vectors)
          - dense_records: 所有批次的 ChunkRecord 合并（顺序与输入一致）
          - sparse_vectors: 所有批次的 SparseVector 合并（顺序与输入一致）

        处理流程：
          1. 空列表 → 返回 ([], [])
          2. 分 batch：[0:bs], [bs:2*bs], ...
          3. 逐批：DenseEncoder.encode(batch) + SparseEncoder.encode(batch)
          4. 合并结果（保持顺序）
          5. trace 记录批次数据
        """
        # 1. 空输入
        if not chunks:
            if trace is not None:
                trace.record_stage("batch_processor", {
                    "total_chunks": 0,
                    "total_batches": 0,
                    "batch_size": self._batch_size,
                })
            return ([], [])

        # 2. 分 batch
        batches = self._split_batches(chunks)

        # 3. 逐批处理
        all_dense: list[ChunkRecord] = []
        all_sparse: list[SparseVector] = []
        batch_results: list[BatchResult] = []

        for batch_idx, batch in enumerate(batches):
            start_time = time.monotonic()

            # Dense 编码（如果编码器可用）
            dense_records: list[ChunkRecord] = []
            if self._dense_encoder is not None:
                dense_records = self._dense_encoder.encode(batch)

            # Sparse 编码
            sparse_vectors = self._sparse_encoder.encode(batch)

            # 合并到总结果
            all_dense.extend(dense_records)
            all_sparse.extend(sparse_vectors)

            elapsed_ms = (time.monotonic() - start_time) * 1000
            batch_results.append(BatchResult(
                batch_index=batch_idx,
                chunk_count=len(batch),
                dense_count=len(dense_records),
                sparse_count=len(sparse_vectors),
                duration_ms=round(elapsed_ms, 2),
            ))

        # 4. trace 记录
        if trace is not None:
            trace.record_stage("batch_processor", {
                "total_chunks": len(chunks),
                "total_batches": len(batches),
                "batch_size": self._batch_size,
                "batches": [
                    {
                        "index": br.batch_index,
                        "chunks": br.chunk_count,
                        "dense": br.dense_count,
                        "sparse": br.sparse_count,
                        "duration_ms": br.duration_ms,
                    }
                    for br in batch_results
                ],
            })

        logger.info(
            "BatchProcessor: %d chunks → %d batches (batch_size=%d), "
            "dense=%d, sparse=%d",
            len(chunks),
            len(batches),
            self._batch_size,
            len(all_dense),
            len(all_sparse),
        )

        return (all_dense, all_sparse)

    # --------------------------------------------------------
    # 分批逻辑
    # --------------------------------------------------------

    def _split_batches(self, chunks: list[Chunk]) -> list[list[Chunk]]:
        """将 chunks 按顺序分成多个 batch

        接口签名：_split_batches(chunks) -> list[list[Chunk]]
        出参：batch 列表，每个 batch 是 chunk 子列表

        知识点：分批策略
          - 按顺序切分（保持 chunk 顺序稳定）
          - batch_size=2, 5 chunks → [[c0,c1], [c2,c3], [c4]]
          - 面试考点："为什么要保持顺序？" → 检索结果需要按 chunk 顺序展示
        """
        bs = self._batch_size
        return [chunks[i:i + bs] for i in range(0, len(chunks), bs)]

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def batch_size(self) -> int:
        """每批最大 chunk 数"""
        return self._batch_size

    @property
    def dense_encoder(self) -> DenseEncoder | None:
        """Dense 编码器实例（可能为 None）"""
        return self._dense_encoder

    @property
    def sparse_encoder(self) -> SparseEncoder:
        """Sparse 编码器实例"""
        return self._sparse_encoder

