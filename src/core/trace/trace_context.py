"""
TraceContext — 追踪上下文（C5 最小实现，Phase F 完善）

知识点：TraceContext 是可观测性的核心数据结构
  - trace_id: 唯一标识一次完整请求（Query 或 Ingestion）
  - stages[]: 记录每个阶段的名称、耗时、中间结果
  - 用途：调试"为什么召回了这个文档"、性能分析

当前阶段（C5）最小实现：
  - 生成 trace_id（uuid4）
  - record_stage 存储阶段数据
  - finish 汇总（返回 dict）
  - Phase F 阶段会扩展为完整的 Tracing 系统（OTLP 导出等）

接口签名：
  TraceContext(trace_id: str | None = None)
  record_stage(stage: str, data: dict, duration_ms: float | None = None) -> None
  finish() -> dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


# ============================================================
# StageRecord — 阶段记录
# ============================================================

@dataclass
class StageRecord:
    """单个阶段的执行记录

    接口签名：StageRecord(stage, data, duration_ms, timestamp)
    字段说明：
      - stage: 阶段名称（如 "chunk_refiner"）
      - data: 阶段产出的元数据（如 {"refined_count": 10, "fallback_count": 1}）
      - duration_ms: 阶段耗时（毫秒）
      - timestamp: 记录时间（ISO 8601）
    """
    stage: str
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================
# TraceContext — 追踪上下文
# ============================================================

class TraceContext:
    """追踪上下文 — 贯穿一次请求的全生命周期

    知识点：TraceContext 的设计
      - trace_id: 唯一标识一次请求（Ingestion 或 Query）
      - stages[]: 按时间顺序记录每个阶段的执行数据
      - record_stage: 由各组件主动调用，记录自己的阶段数据
      - finish: 汇总所有阶段，返回可序列化的 dict（用于日志/导出）

    最小实现（C5 阶段）：
      - 只提供内存存储（不持久化）
      - Phase F 阶段会扩展：导出到 JSONL、支持 OTLP、分布式追踪等
      - 面试考点："为什么需要 TraceContext？" → 调试 + 性能分析 + 可观测性

    使用方式：
      trace = TraceContext()
      trace.record_stage("loader", {"path": "/doc.pdf"})
      trace.record_stage("chunker", {"count": 5}, duration_ms=12.3)
      summary = trace.finish()  # 返回汇总 dict
    """

    def __init__(self, trace_id: str | None = None) -> None:
        """初始化 TraceContext

        接口签名：TraceContext(trace_id: str | None = None)
        入参：
          - trace_id: 可选，自定义 trace_id；不传则自动生成 uuid4
        """
        self.trace_id: str = trace_id or uuid4().hex
        self.stages: list[StageRecord] = []
        self._start_time: float = time.perf_counter()

    def record_stage(
        self,
        stage: str,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """记录一个阶段的执行数据

        接口签名：record_stage(stage, data, duration_ms) -> None
        入参：
          - stage: 阶段名称（如 "chunk_refiner"）
          - data: 阶段元数据（可选）
          - duration_ms: 阶段耗时毫秒（可选）
        """
        self.stages.append(
            StageRecord(
                stage=stage,
                data=data or {},
                duration_ms=duration_ms,
            )
        )

    def finish(self) -> dict[str, Any]:
        """汇总所有阶段，返回可序列化的 dict

        接口签名：finish() -> dict
        出参：包含 trace_id、stages 列表、总耗时的 dict

        知识点：为什么 finish 返回 dict 而非对象？
          - dict 可直接 JSON 序列化，便于日志/导出
          - 与 OTLP/Prometheus 等可观测性标准兼容
          - Phase F 扩展时只需增加字段，不破坏接口
        """
        total_duration_ms = (time.perf_counter() - self._start_time) * 1000
        return {
            "trace_id": self.trace_id,
            "stages": [
                {
                    "stage": s.stage,
                    "data": s.data,
                    "duration_ms": s.duration_ms,
                    "timestamp": s.timestamp,
                }
                for s in self.stages
            ],
            "total_duration_ms": round(total_duration_ms, 2),
        }

    def get_stages(self, stage_name: str) -> list[StageRecord]:
        """获取指定名称的所有阶段记录（一个阶段可能被多次记录）

        接口签名：get_stages(stage_name) -> list[StageRecord]
        """
        return [s for s in self.stages if s.stage == stage_name]

    def __repr__(self) -> str:
        return f"TraceContext(trace_id={self.trace_id[:8]}..., stages={len(self.stages)})"

