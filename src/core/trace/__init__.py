# 追踪上下文 — trace_id 生成 + 阶段记录 + finish 汇总
# 知识点：TraceContext 是可观测性的核心数据结构
#   - trace_id: 唯一标识一次完整请求（Query 或 Ingestion）
#   - stages[]: 记录每个阶段的名称、耗时、中间结果
#   - 用途：调试"为什么召回了这个文档"、性能分析

from core.trace.trace_context import StageRecord, TraceContext

__all__ = [
    "TraceContext",
    "StageRecord",
]

