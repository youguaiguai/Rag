"""
VectorUpserter — 向量存储与幂等性保证

知识点：VectorUpserter 在 RAG Pipeline 中的位置
  - 摄取链路：... → DenseEncoder → **VectorUpserter** → 向量数据库
  - 职责：接收 ChunkRecord，转换为 VectorRecord，调用 BaseVectorStore.upsert() 幂等写入
  - 为 D2 (DenseRetriever) 提供可查询的向量数据库

幂等性设计（面试考点）：
  - chunk_id = hash(source_path + chunk_index + content_hash[:8])
  - 同一内容重复 upsert → id 不变 → 覆盖旧记录（不产生重复）
  - 内容变更 → content_hash 变化 → id 变化 → 新记录（旧记录需手动删除或 GC）
  - 面试考点："upsert 和 insert 的区别？" → upsert 幂等，相同 id 覆盖

ChunkRecord → VectorRecord 转换：
  - chunk_id → id（字段重命名）
  - embedding → embedding（直接复制）
  - text → text（直接复制）
  - metadata → metadata（合并 doc_id 和 source_ref 到 metadata）
  - 使用 record_to_vector_record() 工具函数

接口签名：
  VectorUpserter(settings: Settings, vector_store: BaseVectorStore | None = None)
  upsert(records: list[ChunkRecord], trace: TraceContext | None = None) -> int
"""

from __future__ import annotations

import logging
from core.types import ChunkRecord, record_to_vector_record
from libs.vector_store.base_vector_store import BaseVectorStore, VectorRecord, VectorStoreError
from libs.vector_store.vector_store_factory import VectorStoreFactory
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext

logger = logging.getLogger(__name__)


class VectorUpserter:
    """向量存储器 — 将 ChunkRecord 幂等写入向量数据库

    知识点：VectorUpserter 的设计原则
      1. 幂等性：相同内容多次写入不产生重复（基于 chunk_id 的 upsert）
      2. 批量写入：一次 upsert 多条记录，减少数据库交互
      3. 顺序保证：输出顺序与输入一致
      4. 异常隔离：写入失败抛 VectorStoreError（存储层不可降级）

    接口签名：
      VectorUpserter(settings, vector_store=None)
      upsert(records, trace=None) -> int  # 返回写入数量
    """

    def __init__(
        self,
        settings: Settings,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        """初始化 VectorUpserter

        接口签名：VectorUpserter(settings: Settings, vector_store: BaseVectorStore | None = None)
        入参：
          - settings: 全局配置（含 vector_store 配置）
          - vector_store: 可选的 BaseVectorStore 实例（测试注入优先）
        """
        self._settings = settings

        # VectorStore 实例：注入优先；未注入时从工厂创建
        self._store: BaseVectorStore = vector_store  # type: ignore[assignment]
        if self._store is None:
            self._store = VectorStoreFactory.create(settings.vector_store)

    # --------------------------------------------------------
    # 主入口：upsert
    # --------------------------------------------------------

    def upsert(
        self,
        records: list[ChunkRecord],
        trace: TraceContext | None = None,
    ) -> int:
        """将 ChunkRecord 列表幂等写入向量数据库

        接口签名：upsert(records: list[ChunkRecord], trace=None) -> int
        入参：
          - records: DenseEncoder 输出的 ChunkRecord 列表
          - trace: 可选追踪上下文
        出参：写入的记录数量
        异常：VectorStoreError — 写入失败

        处理流程：
          1. 空列表 → 返回 0（不调用数据库）
          2. ChunkRecord → VectorRecord 转换
          3. 调用 BaseVectorStore.upsert() 批量写入
          4. trace 记录阶段数据

        幂等性保证：
          - chunk_id 作为 VectorRecord.id（确定性生成）
          - 相同 id 的 upsert 覆盖旧记录
          - 面试考点："重复运行会怎样？" → 幂等，覆盖不重复
        """
        # 1. 空输入
        if not records:
            if trace is not None:
                trace.record_stage("vector_upserter", {"total": 0})
            return 0

        # 2. 转换为 VectorRecord
        vector_records: list[VectorRecord] = []
        for record in records:
            vr = record_to_vector_record(record)
            vector_records.append(vr)

        # 3. 批量写入
        self._store.upsert(vector_records)

        # 4. trace 记录
        if trace is not None:
            trace.record_stage("vector_upserter", {
                "total": len(vector_records),
                "ids": [vr.id for vr in vector_records],
            })

        logger.info(
            "VectorUpserter: %d 条记录写入完成 (store=%s)",
            len(vector_records),
            type(self._store).__name__,
        )

        return len(vector_records)

    # --------------------------------------------------------
    # 辅助方法
    # --------------------------------------------------------

    def delete(self, chunk_ids: list[str]) -> int:
        """按 chunk_id 删除向量记录

        接口签名：delete(chunk_ids: list[str]) -> int
        出参：实际删除的记录数

        知识点：删除场景
          - 文档更新时删除旧 chunk 的向量
          - 文档下架时删除所有关联向量
          - 面试考点："为什么需要删除？" → 内容变更后旧向量已失效
        """
        return self._store.delete(chunk_ids)

    def delete_by_doc_id(self, doc_id: str) -> int:
        """按 doc_id 删除文档的所有向量记录

        接口签名：delete_by_doc_id(doc_id: str) -> int
        出参：删除的记录数

        知识点：按 metadata 删除
          - doc_id 在写入时合并到 metadata
          - 一次调用删除整个文档的所有 chunk
        """
        return self._store.delete_by_metadata({"doc_id": doc_id})

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def vector_store(self) -> BaseVectorStore:
        """底层 VectorStore 实例"""
        return self._store

