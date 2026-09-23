"""
TraceContext — 追踪上下文（F1 增强版）

知识点：TraceContext 是可观测性的核心数据结构
  - trace_id: 唯一标识一次完整请求（Query 或 Ingestion）
  - trace_type: 区分请求类型（"query" 或 "ingestion"）
  - stages[]: 记录每个阶段的名称、耗时、中间结果
  - 用途：调试"为什么召回了这个文档"、性能分析

F1 增强功能：
  - trace_type: 区分 query/ingestion 类型
  - finish(): 标记 trace 结束，计算总耗时
  - elapsed_ms(): 获取指定阶段或总耗时
  - to_dict(): 序列化为可 JSON 输出的字典

接口签名：
  TraceContext(trace_id: str | None = None, trace_type: str = "query")
  record_stage(stage: str, data: dict, duration_ms: float | None = None) -> None
  finish() -> None
  elapsed_ms(stage_name: str | None = None) -> float
  to_dict() -> dict
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
      - trace_id: 唯一标识一次请求
      - trace_type: "query" 或 "ingestion"
      - stages[]: 按时间顺序记录每个阶段的执行数据
      - record_stage: 由各组件主动调用
      - finish: 标记结束，计算总耗时
      - to_dict: 序列化为可 JSON 输出的字典

    使用方式：
      trace = TraceContext(trace_type="query")
      trace.record_stage("loader", {"path": "/doc.pdf"})
      trace.record_stage("chunker", {"count": 5}, duration_ms=12.3)
      trace.finish()
      summary = trace.to_dict()
    """

    def __init__(
        self,
        trace_id: str | None = None,
        trace_type: str = "query",
    ) -> None:
        """初始化 TraceContext

        接口签名：TraceContext(trace_id=None, trace_type="query")
        入参：
          - trace_id: 可选，自定义 trace_id；不传则自动生成 uuid4
          - trace_type: 请求类型，"query" 或 "ingestion"（默认 "query"）
        """
        self.trace_id: str = trace_id or uuid4().hex
        self.trace_type: str = trace_type
        self.stages: list[StageRecord] = []
        self._start_time: float = time.perf_counter()
        self._finished: bool = False
        self._end_time: float | None = None
        self.started_at: str = datetime.now(timezone.utc).isoformat()

    def record_stage(
        self,
        stage: str,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """记录一个阶段的执行数据

        接口签名：record_stage(stage, data, duration_ms) -> None
        """
        self.stages.append(
            StageRecord(
                stage=stage,
                data=data or {},
                duration_ms=duration_ms,
            )
        )

    def finish(self) -> None:
        """标记 trace 结束，计算总耗时

        接口签名：finish() -> None
        行为：设置 _finished 标志，记录结束时间

        知识点：finish 与 to_dict 的关系
          - finish 标记 trace 结束（幂等：多次调用无副作用）
          - to_dict 序列化输出（无论是否调用 finish 都可用）
          - 面试考点："为什么 finish 不返回 dict？" → 关注点分离：finish 改状态，to_dict 做序列化
        """
        if not self._finished:
            self._finished = True
            self._end_time = time.perf_counter()

    def elapsed_ms(self, stage_name: str | None = None) -> float:
        """获取指定阶段或总耗时

        接口签名：elapsed_ms(stage_name: str | None = None) -> float
        入参：
          - stage_name: 阶段名称。None 表示总耗时，指定名称表示该阶段累计耗时
        出参：耗时（毫秒）

        知识点：耗时计算
          - 总耗时：从创建到 finish()（或当前时间，如果未 finish）
          - 阶段耗时：所有同名 stage 的 duration_ms 之和
          - 面试考点："elapsed_ms 和 duration_ms 的区别？" → duration_ms 是调用方传入的，elapsed_ms 是 TraceContext 计算的
        """
        if stage_name is None:
            # 总耗时
            end = self._end_time if self._finished else time.perf_counter()
            return round((end - self._start_time) * 1000, 2)

        # 指定阶段的累计耗时
        total = sum(
            s.duration_ms for s in self.stages
            if s.stage == stage_name and s.duration_ms is not None
        )
        return round(total, 2)

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 输出的字典

        接口签名：to_dict() -> dict
        出参：包含 trace_id、trace_type、started_at、finished_at、total_elapsed_ms、stages

        知识点：序列化设计
          - 所有字段都是 JSON 兼容类型（str/int/float/list/dict）
          - 可直接 json.dumps() 输出
          - 面试考点："为什么 to_dict 而非 __dict__？" → 控制输出格式 + 计算派生字段
        """
        end_time = self._end_time if self._finished else time.perf_counter()
        total_elapsed_ms = round((end_time - self._start_time) * 1000, 2)
        finished_at = (
            datetime.now(timezone.utc).isoformat() if self._finished else None
        )

        return {
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "total_elapsed_ms": total_elapsed_ms,
            "stages": [
                {
                    "stage": s.stage,
                    "data": s.data,
                    "duration_ms": s.duration_ms,
                    "timestamp": s.timestamp,
                }
                for s in self.stages
            ],
        }

    def get_stages(self, stage_name: str) -> list[StageRecord]:
        """获取指定名称的所有阶段记录

        接口签名：get_stages(stage_name) -> list[StageRecord]
        """
        return [s for s in self.stages if s.stage == stage_name]

    def __repr__(self) -> str:
        return f"TraceContext(trace_id={self.trace_id[:8]}..., type={self.trace_type}, stages={len(self.stages)})"

