"""
TraceService — Trace 读取服务

知识点：TraceService 的设计
  - 读取 logs/traces_*.jsonl 文件
  - 解析为结构化 Trace 对象
  - 支持按 trace_type 过滤 / 按时间排序
  - 面试考点："为什么用 JSONL？" → 支持 append 写入 + 按行读取
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TraceRecord:
    """解析后的 Trace 记录"""
    trace_id: str
    trace_type: str
    started_at: str = ""
    finished_at: str | None = None
    total_elapsed_ms: float = 0.0
    stages: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class TraceService:
    """Trace 读取服务 — 从 JSONL 文件读取 Trace 数据

    知识点：TraceService 的使用场景
      - Ingestion Traces 页面：展示摄取历史 + 耗时瀑布图
      - Query Traces 页面：展示查询历史 + Dense/Sparse 对比
    """

    def __init__(self, logs_dir: str = "logs") -> None:
        """
        入参：logs_dir — 日志目录路径
        """
        self._logs_dir = Path(logs_dir)

    def list_traces(
        self,
        trace_type: str | None = None,
        limit: int = 50,
    ) -> list[TraceRecord]:
        """列出 Trace 记录

        接口签名：list_traces(trace_type=None, limit=50) -> list[TraceRecord]
        入参：
          - trace_type: 过滤类型（"query" / "ingestion" / None=全部）
          - limit: 最大返回数
        出参：TraceRecord 列表（按时间倒序）
        """
        all_records: list[TraceRecord] = []

        if not self._logs_dir.exists():
            return all_records

        # 读取所有 JSONL 文件
        for jsonl_file in sorted(self._logs_dir.glob("traces_*.jsonl"), reverse=True):
            try:
                records = self._read_jsonl(jsonl_file, trace_type)
                all_records.extend(records)
            except Exception as e:
                logger.warning("TraceService: 读取失败 %s: %s", jsonl_file, e)

        # 按时间倒序 + 截断
        all_records.sort(key=lambda r: r.started_at, reverse=True)
        return all_records[:limit]

    def get_trace_detail(self, trace_id: str) -> TraceRecord | None:
        """获取单个 Trace 详情

        接口签名：get_trace_detail(trace_id) -> TraceRecord | None
        """
        if not self._logs_dir.exists():
            return None

        for jsonl_file in self._logs_dir.glob("traces_*.jsonl"):
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        if data.get("trace_id") == trace_id:
                            return self._parse_record(data)
            except Exception:
                continue

        return None

    def _read_jsonl(
        self,
        file_path: Path,
        trace_type: str | None = None,
    ) -> list[TraceRecord]:
        """读取 JSONL 文件

        接口签名：_read_jsonl(file_path, trace_type) -> list[TraceRecord]
        """
        records: list[TraceRecord] = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if trace_type and data.get("trace_type") != trace_type:
                        continue
                    records.append(self._parse_record(data))
                except json.JSONDecodeError:
                    continue

        return records

    def _parse_record(self, data: dict[str, Any]) -> TraceRecord:
        """解析 JSON 数据为 TraceRecord

        接口签名：_parse_record(data: dict) -> TraceRecord
        """
        return TraceRecord(
            trace_id=data.get("trace_id", ""),
            trace_type=data.get("trace_type", "unknown"),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at"),
            total_elapsed_ms=data.get("total_elapsed_ms", 0.0),
            stages=data.get("stages", []),
            raw=data,
        )

