"""
结构化日志模块 — 占位实现

知识点：
  - 结构化日志：JSON 格式，方便 ELK/Splunk 等日志系统解析
  - 可查询：按字段精确过滤（如 trace_id="xxx"）
  - 与 Trace 系统联动：日志中包含 trace_id，串联请求链路

当前阶段（A3）仅提供最小实现：
  - get_logger() 返回标准 logging.Logger
  - 输出到 stderr（MCP Server 通过 stdio 通信，日志走 stderr 避免干扰协议）
  - 后续阶段会升级为 JSON Formatter

接口签名：
  get_logger(name: str = "rag", level: str = "INFO") -> logging.Logger
    入参：logger 名称、日志级别
    出参：标准 logging.Logger 实例
"""

import logging
import sys


def get_logger(name: str = "rag", level: str = "INFO") -> logging.Logger:
    """获取 Logger 实例

    接口签名：get_logger(name: str = "rag", level: str = "INFO") -> logging.Logger

    知识点：为什么 MCP Server 日志走 stderr？
      - MCP 协议使用 stdio（stdin/stdout）传输 JSON-RPC 消息
      - 如果日志写到 stdout，会污染 JSON-RPC 消息流，导致协议解析失败
      - stderr 是 MCP 规范推荐的日志输出通道
      - 面试考点："MCP Server 为什么不能 print()？" → stdout 被 JSON-RPC 占用

    参数：
      name: Logger 名称，通常用模块名（如 "rag.core.settings"）
      level: 日志级别，默认 INFO
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler（get_logger 可能被多次调用）
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger
