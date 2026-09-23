"""
TraceContext + TraceCollector 单元测试 — F1: Trace 基础设施增强

测试覆盖：
  - TraceContext 增强功能（trace_type/finish/elapsed_ms/to_dict）
  - TraceCollector 收集和持久化
"""

from __future__ import annotations

import json
import pytest
import sys
from pathlib import Path

# 确保 src/ 在路径中
_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from core.trace.trace_context import TraceContext, StageRecord
from core.trace.trace_collector import TraceCollector


# ============================================================
# TestTraceContextEnhanced — TraceContext 增强功能测试
# ============================================================

class TestTraceContextEnhanced:
    """TraceContext 增强功能测试（14 个测试）"""

    def test_default_trace_type_is_query(self) -> None:
        """默认 trace_type 为 query"""
        trace = TraceContext()
        assert trace.trace_type == "query"

    def test_custom_trace_type(self) -> None:
        """可设置 trace_type 为 ingestion"""
        trace = TraceContext(trace_type="ingestion")
        assert trace.trace_type == "ingestion"

    def test_custom_trace_id(self) -> None:
        """可使用自定义 trace_id"""
        trace = TraceContext(trace_id="my_custom_id_123")
        assert trace.trace_id == "my_custom_id_123"

    def test_finish_sets_finished_flag(self) -> None:
        """finish 设置 _finished 标志"""
        trace = TraceContext()
        assert trace._finished is False
        trace.finish()
        assert trace._finished is True

    def test_finish_is_idempotent(self) -> None:
        """finish 幂等：多次调用无副作用"""
        trace = TraceContext()
        trace.record_stage("s1", {})
        trace.finish()
        trace.record_stage("s2", {})  # finish 后应该不能再记录（但 Python 不会阻止）
        trace.finish()  # 第二次调用不出错
        assert trace._finished is True

    def test_elapsed_ms_total(self) -> None:
        """elapsed_ms() 返回总耗时"""
        trace = TraceContext()
        trace.record_stage("s1", {}, duration_ms=10.0)
        elapsed = trace.elapsed_ms()
        assert elapsed >= 0

    def test_elapsed_ms_stage(self) -> None:
        """elapsed_ms(stage_name) 返回指定阶段累计耗时"""
        trace = TraceContext()
        trace.record_stage("search", {}, duration_ms=15.0)
        trace.record_stage("search", {}, duration_ms=25.0)
        trace.record_stage("rerank", {}, duration_ms=10.0)

        assert trace.elapsed_ms("search") == 40.0
        assert trace.elapsed_ms("rerank") == 10.0
        assert trace.elapsed_ms("nonexistent") == 0.0

    def test_to_dict_contains_required_fields(self) -> None:
        """to_dict 输出包含必需字段"""
        trace = TraceContext(trace_type="query")
        trace.record_stage("s1", {"key": "val"}, duration_ms=5.0)
        trace.finish()

        d = trace.to_dict()

        assert "trace_id" in d
        assert "trace_type" in d
        assert "started_at" in d
        assert "finished_at" in d
        assert "total_elapsed_ms" in d
        assert "stages" in d

    def test_to_dict_trace_type_matches(self) -> None:
        """to_dict 的 trace_type 与初始化一致"""
        trace = TraceContext(trace_type="ingestion")
        d = trace.to_dict()
        assert d["trace_type"] == "ingestion"

    def test_to_dict_stages_format(self) -> None:
        """to_dict 的 stages 格式正确"""
        trace = TraceContext()
        trace.record_stage("loader", {"file": "test.pdf"}, duration_ms=5.5)

        d = trace.to_dict()
        assert len(d["stages"]) == 1

        stage = d["stages"][0]
        assert stage["stage"] == "loader"
        assert stage["data"] == {"file": "test.pdf"}
        assert stage["duration_ms"] == 5.5
        assert "timestamp" in stage

    def test_to_dict_finished_at_is_set(self) -> None:
        """调用 finish 后 to_dict 的 finished_at 有值"""
        trace = TraceContext()
        trace.finish()
        d = trace.to_dict()
        assert d["finished_at"] is not None

    def test_to_dict_finished_at_none_before_finish(self) -> None:
        """未 finish 时 to_dict 的 finished_at 为 None"""
        trace = TraceContext()
        d = trace.to_dict()
        assert d["finished_at"] is None

    def test_to_dict_is_json_serializable(self) -> None:
        """to_dict 输出可 JSON 序列化"""
        trace = TraceContext(trace_type="query")
        trace.record_stage("s1", {"count": 10, "name": "test"}, duration_ms=5.0)
        trace.finish()

        d = trace.to_dict()
        # 不应抛异常
        json_str = json.dumps(d)
        assert len(json_str) > 0

        # 反序列化验证
        parsed = json.loads(json_str)
        assert parsed["trace_id"] == trace.trace_id

    def test_total_elapsed_ms_in_dict(self) -> None:
        """to_dict 的 total_elapsed_ms 合理"""
        trace = TraceContext()
        trace.record_stage("s1")
        trace.finish()

        d = trace.to_dict()
        assert d["total_elapsed_ms"] >= 0


# ============================================================
# TestTraceCollector — 追踪收集器测试
# ============================================================

class TestTraceCollector:
    """TraceCollector 测试（6 个测试）"""

    def test_collect_calls_finish(self) -> None:
        """collect 调用 trace.finish()"""
        collector = TraceCollector(log_dir=None)
        trace = TraceContext()

        collector.collect(trace)

        assert trace._finished is True
        assert collector.trace_count == 1

    def test_collect_without_persistence(self) -> None:
        """log_dir=None 时只内存收集"""
        collector = TraceCollector(log_dir=None)
        trace = TraceContext()
        trace.record_stage("s1", {})

        collector.collect(trace)

        assert collector.trace_count == 1

    def test_collect_with_persistence(self, tmp_path: Path) -> None:
        """持久化到 JSONL 文件"""
        collector = TraceCollector(log_dir=str(tmp_path))
        trace = TraceContext()
        trace.record_stage("s1", {"key": "val"}, duration_ms=5.0)

        collector.collect(trace)

        # 检查文件是否生成
        jsonl_files = list(tmp_path.glob("traces_*.jsonl"))
        assert len(jsonl_files) == 1

        # 验证内容
        content = jsonl_files[0].read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 1

        parsed = json.loads(lines[0])
        assert parsed["trace_id"] == trace.trace_id

    def test_collect_multiple_traces(self) -> None:
        """收集多个 trace"""
        collector = TraceCollector(log_dir=None)

        for i in range(3):
            trace = TraceContext()
            trace.record_stage(f"s{i}", {})
            collector.collect(trace)

        assert collector.trace_count == 3

    def test_flush_is_noop_when_persisting(self, tmp_path: Path) -> None:
        """flush 不报错（持久化模式下是空操作）"""
        collector = TraceCollector(log_dir=str(tmp_path))
        # 不应抛异常
        collector.flush()

    def test_collected_traces_list(self) -> None:
        """collect 后的 traces 列表正确"""
        collector = TraceCollector(log_dir=None)
        trace1 = TraceContext()
        trace1.record_stage("a", {})
        trace2 = TraceContext()
        trace2.record_stage("b", {})

        collector.collect(trace1)
        collector.collect(trace2)

        assert collector.trace_count == 2

