"""
DenseEncoder — 稠密向量编码器（Chunk → ChunkRecord）

知识点：DenseEncoder 在 RAG Pipeline 中的位置
  - 摄取链路：Loader → Splitter → Transform 链 → **DenseEncoder** → VectorUpserter
  - 职责：将 Chunk.text 批量送入 BaseEmbedding，生成向量，组合成 ChunkRecord
  - 与 Transform 的区别：Transform 是"增强"（可选/降级），Encoder 是"编码"（必需/失败抛异常）

设计要点（面试考点）：
  1. 批量处理：一次 embed 所有 chunk 文本，减少 API 调用次数
  2. 维度校验：编码后验证向量维度与 embedding.dimensions 一致
  3. 数量校验：输出向量数量必须与输入 chunk 数量一致
  4. 空输入处理：空列表 → 空列表输出（不调用 API）

接口签名：
  DenseEncoder(settings: Settings, embedding: BaseEmbedding | None = None)
  encode(chunks: list[Chunk], trace: TraceContext | None = None) -> list[ChunkRecord]

Chunk → ChunkRecord 映射：
  chunk_id    → chunk_id（一致，用于幂等 upsert）
  doc_id      → doc_id
  text        → text（用于 BM25 索引和检索展示）
  embedding   → embedding（新增，由 DenseEncoder 生成）
  metadata    → metadata
  source_ref  → source_ref
"""

from __future__ import annotations

import logging
from core.types import Chunk, ChunkRecord, chunk_to_record
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from libs.embedding.embedding_factory import EmbeddingFactory
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext

logger = logging.getLogger(__name__)


class DenseEncoder:
    """稠密向量编码器 — 将 Chunk.text 批量编码为向量

    知识点：为什么 Encoder 不继承 BaseTransform？
      - Transform 是"增强"环节：可选、降级安全、不阻塞
      - Encoder 是"编码"环节：必需、失败应抛异常（无法跳过）
      - 接口不同：Transform.transform(Chunk→Chunk)，Encoder.encode(Chunk→ChunkRecord)
      - 面试考点："Encoder 和 Transform 的区别？" → 职责不同 + 失败策略不同

    接口签名：
      DenseEncoder(settings, embedding=None)
      encode(chunks, trace=None) -> list[ChunkRecord]
    """

    def __init__(
        self,
        settings: Settings,
        embedding: BaseEmbedding | None = None,
    ) -> None:
        """初始化 DenseEncoder

        接口签名：DenseEncoder(settings: Settings, embedding: BaseEmbedding | None = None)
        入参：
          - settings: 全局配置（含 embedding 配置）
          - embedding: 可选的 BaseEmbedding 实例（测试注入优先）
        """
        self._settings = settings

        # Embedding 实例：注入优先；未注入时从工厂创建
        self._embedding: BaseEmbedding = embedding  # type: ignore[assignment]
        if self._embedding is None:
            self._embedding = EmbeddingFactory.create(settings.embedding)

        # 预期维度（用于校验）
        self._expected_dims: int = self._embedding.dimensions

    # --------------------------------------------------------
    # 主入口：encode
    # --------------------------------------------------------

    def encode(
        self,
        chunks: list[Chunk],
        trace: TraceContext | None = None,
    ) -> list[ChunkRecord]:
        """将 Chunk 列表批量编码为 ChunkRecord 列表

        接口签名：encode(chunks: list[Chunk], trace=None) -> list[ChunkRecord]
        入参：
          - chunks: 待编码的 Chunk 列表
          - trace: 可选追踪上下文
        出参：ChunkRecord 列表（数量与输入一致，维度与 embedding.dimensions 一致）
        异常：
          - EmbeddingError: API 调用失败 / 维度不匹配 / 数量不一致

        处理流程：
          1. 空列表 → 直接返回空列表（不调用 API）
          2. 提取 chunk.text 列表
          3. 批量调用 embedding.embed()
          4. 校验：向量数量 == chunk 数量
          5. 校验：每个向量维度 == expected_dims
          6. 组装 ChunkRecord（通过 chunk_to_record）
          7. trace 记录阶段数据
        """
        # 1. 空输入处理
        if not chunks:
            if trace is not None:
                trace.record_stage("dense_encoder", {"total": 0, "dims": self._expected_dims})
            return []

        # 2. 提取文本
        texts = [chunk.text for chunk in chunks]

        # 3. 批量编码
        vectors = self._embedding.embed(texts)

        # 4. 数量校验
        if len(vectors) != len(chunks):
            raise EmbeddingError(
                f"编码数量不一致：输入 {len(chunks)} 个 chunk，得到 {len(vectors)} 个向量"
            )

        # 5. 维度校验
        for i, vec in enumerate(vectors):
            if len(vec) != self._expected_dims:
                raise EmbeddingError(
                    f"维度不匹配：chunk[{i}] 向量维度 {len(vec)}，"
                    f"预期 {self._expected_dims}"
                )

        # 6. 组装 ChunkRecord
        records: list[ChunkRecord] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            records.append(chunk_to_record(chunk, vector))

        # 7. trace 记录
        if trace is not None:
            trace.record_stage(
                "dense_encoder",
                {
                    "total": len(records),
                    "dims": self._expected_dims,
                    "model": self._embedding.model_name,
                },
            )

        logger.info(
            "DenseEncoder: 编码完成，%d 个 chunk → %d 维向量 (model=%s)",
            len(records),
            self._expected_dims,
            self._embedding.model_name,
        )

        return records

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def embedding(self) -> BaseEmbedding:
        """底层 Embedding 实例"""
        return self._embedding

    @property
    def dimensions(self) -> int:
        """向量维度"""
        return self._expected_dims

    @property
    def model_name(self) -> str:
        """Embedding 模型名称"""
        return self._embedding.model_name

