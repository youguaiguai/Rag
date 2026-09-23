"""
追踪收集器 — 收集 trace 并持久化

知识点：TraceCollector 的职责
  - 收集 TraceContext 实例
  - 可选持久化到文件（JSON Lines 格式）
  - 面试考点："为什么要单独的 Collector？" → 解耦 TraceContext 创建和持久化逻辑

JSON Lines 格式（每行一个 JSON 对象）：
  {"trace_id": "...", "trace_type": "query", ...}
  {"trace_id": "...", "trace_type": "ingestion", ...}

接口签名：
  TraceCollector(log_dir: str = "logs")
  collect(trace: TraceContext) -> None
  flush() -> None
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TraceCollector:
    """追踪收集器 — 收集 trace 并持久化到 JSON Lines

    知识点：TraceCollector 的设计原则
      - 可选持久化：log_dir=None 时只内存收集
      - 向后兼容：不影响现有 TraceContext 的使用方式
      - 面试考点："collect 时为什么要调用 finish()？" → 确保 trace 状态一致
    """

    def __init__(self, log_dir: str | None = "logs") -> None:
        """初始化 TraceCollector

        接口签名：TraceCollector(log_dir="logs")
        入参：
          - log_dir: 日志目录。None 表示不持久化（仅内存收集）
        """
        self._log_dir = Path(log_dir) if log_dir else None
        self._traces: list[dict[str, Any]] = []

        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

    def collect(self, trace: Any) -> None:
        """收集 trace 并持久化

        接口签名：collect(trace: TraceContext) -> None
        入参：TraceContext 实例

        处理流程：
          1. 确保 trace 已 finish
          2. 序列化为 dict
          3. 写入内存列表
          4. 写入 JSONL 文件
        """
        # 确保 trace 已 finish
        if hasattr(trace, "finish"):
            trace.finish()

        trace_dict = trace.to_dict()
        self._traces.append(trace_dict)

        # 持久化到文件
        if self._log_dir:
            self._write_to_file(trace_dict)

        logger.debug(
            "TraceCollector: 收集 trace %s (type=%s, stages=%d)",
            trace_dict["trace_id"][:8],
            trace_dict.get("trace_type", "?"),
            len(trace_dict.get("stages", [])),
        )

    def _write_to_file(self, trace_dict: dict[str, Any]) -> None:
        """写入 JSONL 文件

        知识点：JSON Lines 格式
          - 每行一个 JSON 对象（无逗号、无外层数组）
          - 支持 append 写入（无需读取整个文件）
          - grep/jq 友好（每行独立可解析）
        """
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = self._log_dir / f"traces_{date_str}.jsonl"

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_dict, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.warning("TraceCollector 写入失败: %s", e)

    def flush(self) -> None:
        """刷新缓冲（内存模式时写入文件）

        知识点：flush 的使用场景
          - 内存模式：将所有收集到的 trace 写入文件
          - 持久化模式：无需操作（已实时写入）
        """
        # 当前实现已实时写入，留作扩展接口
        pass

    @property
    def trace_count(self) -> int:
        """返回已收集的 trace 数量"""
        return len(self._traces)

