"""
JSON Lines Logger 单元测试 — F2: 结构化日志

测试覆盖：
  - JSONFormatter
  - get_trace_logger
  - write_trace
"""

from __future__ import annotations

import json
import logging
import pytest
import sys
from pathlib import Path

# 确保 src/ 在路径中
_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from observability.logger import (
    JSONFormatter,
    get_trace_logger,
    write_trace,
)


# ============================================================
# TestJSONFormatter — JSON Formatter 测试
# ============================================================

class TestJSONFormatter:
    """JSONFormatter 测试（4 个测试）"""

    def test_format_returns_valid_json(self) -> None:
        """format 输出合法 JSON"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert "timestamp" in parsed

    def test_format_with_extra_fields(self) -> None:
        """format 包含 extra 字段"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="msg with extra",
            args=(),
            exc_info=None,
        )
        record.trace_id = "abc123"
        record.custom_field = "value"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["trace_id"] == "abc123"
        assert parsed["custom_field"] == "value"

    def test_format_handles_unicode(self) -> None:
        """format 正确处理 Unicode"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Unicode: 中文测试",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["message"] == "Unicode: 中文测试"

    def test_format_non_serializable_extra(self) -> None:
        """format 将不可序列化的 extra 转为字符串"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.obj = object()  # 不可序列化

        output = formatter.format(record)
        parsed = json.loads(output)

        # 应该被转为字符串
        assert isinstance(parsed["obj"], str)


# ============================================================
# TestWriteTrace — write_trace 测试
# ============================================================

class TestWriteTrace:
    """write_trace 函数测试（5 个测试）"""

    def test_write_creates_file(self, tmp_path: Path) -> None:
        """write_trace 创建日志文件"""
        trace = {"trace_id": "abc", "trace_type": "query", "stages": []}
        write_trace(trace, log_dir=str(tmp_path))

        jsonl_files = list(tmp_path.glob("traces_*.jsonl"))
        assert len(jsonl_files) == 1

    def test_write_appends(self, tmp_path: Path) -> None:
        """write_trace 追加写入"""
        write_trace({"trace_id": "1", "trace_type": "query"}, log_dir=str(tmp_path))
        write_trace({"trace_id": "2", "trace_type": "ingestion"}, log_dir=str(tmp_path))

        jsonl_files = list(tmp_path.glob("traces_*.jsonl"))
        content = jsonl_files[0].read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2

    def test_write_content_is_valid_json(self, tmp_path: Path) -> None:
        """写入的内容是合法 JSON"""
        trace = {
            "trace_id": "test-123",
            "trace_type": "query",
            "total_elapsed_ms": 15.5,
            "stages": [{"stage": "search", "data": {"count": 10}}],
        }
        write_trace(trace, log_dir=str(tmp_path))

        jsonl_files = list(tmp_path.glob("traces_*.jsonl"))
        content = jsonl_files[0].read_text()
        parsed = json.loads(content.strip())

        assert parsed["trace_id"] == "test-123"
        assert parsed["trace_type"] == "query"
        assert parsed["total_elapsed_ms"] == 15.5

    def test_write_contains_trace_type(self, tmp_path: Path) -> None:
        """写入的 trace 包含 trace_type 字段"""
        trace = {"trace_id": "x", "trace_type": "ingestion"}
        write_trace(trace, log_dir=str(tmp_path))

        jsonl_files = list(tmp_path.glob("traces_*.jsonl"))
        parsed = json.loads(jsonl_files[0].read_text().strip())
        assert "trace_type" in parsed
        assert parsed["trace_type"] == "ingestion"

    def test_write_creates_directory(self, tmp_path: Path) -> None:
        """write_trace 自动创建目录"""
        log_dir = tmp_path / "nested" / "logs"
        write_trace({"trace_id": "x"}, log_dir=str(log_dir))

        assert log_dir.exists()
        jsonl_files = list(log_dir.glob("traces_*.jsonl"))
        assert len(jsonl_files) == 1


# ============================================================
# TestGetTraceLogger — Trace Logger 测试
# ============================================================

class TestGetTraceLogger:
    """get_trace_logger 测试（3 个测试）"""

    def test_returns_logger(self) -> None:
        """get_trace_logger 返回 Logger 实例"""
        # 使用临时目录避免污染项目
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = get_trace_logger(log_dir=tmpdir)
            assert isinstance(logger, logging.Logger)
            assert logger.name == "rag.trace"

    def test_logger_has_file_handler(self) -> None:
        """Logger 配置了 FileHandler"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = get_trace_logger(log_dir=tmpdir)
            has_file_handler = any(
                isinstance(h, logging.FileHandler) for h in logger.handlers
            )
            assert has_file_handler

    def test_logger_writes_jsonl(self, tmp_path: Path) -> None:
        """Logger 写入 JSONL 格式"""
        # 清除已有 handler（避免单例影响）
        logger = logging.getLogger("rag.trace")
        logger.handlers.clear()

        logger = get_trace_logger(log_dir=str(tmp_path))

        logger.info("test message", extra={"trace_id": "abc"})

        jsonl_files = list(tmp_path.glob("traces_*.jsonl"))
        assert len(jsonl_files) == 1

        content = jsonl_files[0].read_text()
        parsed = json.loads(content.strip())
        assert parsed["message"] == "test message"
        assert parsed["trace_id"] == "abc"

        # 清理
        logger.handlers.clear()

