"""
结构化日志模块 — JSON Lines 格式 + Trace 持久化

知识点：
  - 结构化日志：JSON 格式，方便 ELK/Splunk 等日志系统解析
  - 可查询：按字段精确过滤（如 trace_id="xxx"）
  - 与 Trace 系统联动：日志中包含 trace_id，串联请求链路
  - JSON Lines：每行一个 JSON 对象，支持 append 写入

F2 增强功能：
  - JSONFormatter：自定义 logging Formatter，输出 JSON 格式
  - get_trace_logger()：获取配置了 JSON Lines 输出的 logger
  - write_trace(trace_dict)：将 trace 字典写入 logs/traces.jsonl

接口签名：
  get_logger(name, level) -> logging.Logger  （已有）
  get_trace_logger(log_dir="logs") -> logging.Logger
  write_trace(trace_dict, log_dir="logs") -> None
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# JSONFormatter — JSON 格式日志 Formatter
# ============================================================

class JSONFormatter(logging.Formatter):
    """JSON 格式日志 Formatter

    知识点：JSONFormatter 的设计
      - 将 logging.LogRecord 序列化为 JSON
      - 包含标准字段：timestamp、level、name、message
      - 支持 extra 字段（通过 `logger.info("msg", extra={...})` 传入）
      - 面试考点："为什么用 JSON 而非纯文本？" → 结构化查询 + 与日志系统集成
    """

    def format(self, record: logging.LogRecord) -> str:
        """将 LogRecord 格式化为 JSON 字符串

        接口签名：format(record) -> str
        入参：logging.LogRecord
        出参：JSON 字符串（一行）
        """
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加 extra 字段（如果存在）
        # LogRecord 的自定义属性（非标准属性）会被放入 __dict__
        standard_attrs = {
            "name", "msg", "args", "created", "exc_info", "exc_text",
            "filename", "funcName", "levelname", "levelno", "lineno",
            "module", "msecs", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName",
            "taskName", "getMessage",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                # 只添加可 JSON 序列化的值
                try:
                    json.dumps(value)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# ============================================================
# 标准 Logger（已有功能）
# ============================================================

def get_logger(name: str = "rag", level: str = "INFO") -> logging.Logger:
    """获取 Logger 实例

    接口签名：get_logger(name: str = "rag", level: str = "INFO") -> logging.Logger

    知识点：为什么 MCP Server 日志走 stderr？
      - MCP 协议使用 stdio（stdin/stdout）传输 JSON-RPC 消息
      - 如果日志写到 stdout，会污染 JSON-RPC 消息流，导致协议解析失败
      - stderr 是 MCP 规范推荐的日志输出通道
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


# ============================================================
# Trace Logger（F2 新增）
# ============================================================

def get_trace_logger(log_dir: str = "logs") -> logging.Logger:
    """获取配置了 JSON Lines 输出的 trace logger

    接口签名：get_trace_logger(log_dir: str = "logs") -> logging.Logger
    入参：log_dir — 日志目录
    出参：配置了 JSONFormatter + FileHandler 的 Logger

    知识点：Trace Logger 的用途
      - 专门用于记录 trace 数据（与普通应用日志分离）
      - 输出到 logs/traces.jsonl（按日期分文件）
      - 使用 JSONFormatter 确保每行是合法 JSON
      - 面试考点："为什么 trace 单独一个 logger？" → 关注点分离，trace 数据量大且格式固定
    """
    logger = logging.getLogger("rag.trace")

    # 避免重复添加 handler
    if not logger.handlers:
        # 确保日志目录存在
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        # 按日期分文件
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = Path(log_dir) / f"traces_{date_str}.jsonl"

        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


def write_trace(trace_dict: dict[str, Any], log_dir: str = "logs") -> None:
    """将 trace 字典写入 JSONL 文件

    接口签名：write_trace(trace_dict: dict, log_dir: str = "logs") -> None
    入参：
      - trace_dict: trace.to_dict() 的输出
      - log_dir: 日志目录

    知识点：write_trace 的使用场景
      - TraceCollector.collect() 内部调用
      - 也可独立使用（不通过 TraceCollector）
      - 面试考点："write_trace 和 TraceCollector 的关系？" → write_trace 是底层 IO，TraceCollector 是高层抽象
    """
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = Path(log_dir) / f"traces_{date_str}.jsonl"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_dict, ensure_ascii=False, default=str) + "\n")

    except Exception as e:
        # 写入失败不应影响主流程
        fallback = logging.getLogger("rag")
        fallback.warning("write_trace 失败: %s", e)
