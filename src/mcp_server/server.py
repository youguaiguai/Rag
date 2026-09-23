"""
MCP Server 入口 — Stdio Transport 实现

知识点：MCP (Model Context Protocol) 是 Anthropic 定义的 AI 工具调用协议
  - 通过 Stdio Transport 通信：stdin 接收请求，stdout 返回响应
  - 所有日志必须输出到 stderr，不能污染 stdout（否则会破坏 JSON-RPC 协议）
  - 面试考点："为什么日志不能输出到 stdout？" → stdout 的每一行必须是一个完整的 JSON-RPC 消息

Stdio Transport 约束（核心设计原则）：
  - stdout: 只输出 JSON-RPC 消息（一行一个 JSON 对象）
  - stderr: 所有日志、调试信息、错误堆栈
  - stdin: 读取一行一个 JSON-RPC 请求（LSP 风格）
  - 面试考点："怎么保证 stdout 不被污染？" → logging 只配置 stderr handler

启动与停止：
  - 启动：从 stdin 读取，循环处理直到 EOF 或 quit
  - 停止：stdin 关闭（EOF）时优雅退出

接口签名：
  MCPServer()
  register_tool(name, callable, schema) -> None
  run() -> None  # 阻塞式运行，直到 stdin EOF
  start() -> None  # 非阻塞式启动（用于测试）
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp_server.protocol_handler import ProtocolHandler

logger = logging.getLogger(__name__)


# ============================================================
# MCP Server
# ============================================================

class MCPServer:
    """MCP Server — Stdio Transport 实现

    知识点：MCPServer 的设计原则
      - 单一职责：只做消息循环和 I/O，协议解析委托给 ProtocolHandler
      - Stdio 约束：stdout 只输出 JSON-RPC，日志全部走 stderr
      - 优雅退出：stdin EOF 时正常退出
      - 面试考点："如何实现 graceful shutdown？" → 检测 stdin EOF → break 循环

    接口签名：
      MCPServer()
      register_tool(name, callable, schema) -> None
      run() -> None
    """

    def __init__(self) -> None:
        """初始化 MCP Server

        初始化流程：
          1. 创建 ProtocolHandler 实例
          2. 配置日志输出到 stderr
        """
        self._protocol = ProtocolHandler()
        self._running = False

        # 确保日志输出到 stderr（不污染 stdout）
        self._setup_logging()

    def _setup_logging(self) -> None:
        """配置日志输出到 stderr

        知识点：Stdio Transport 约束
          - stdout 只输出 JSON-RPC 消息
          - 所有日志（包括第三方库日志）必须输出到 stderr
          - 面试考点："怎么防止第三方库日志污染 stdout？" → 根日志 handler 只配 stderr
        """
        root_logger = logging.getLogger()

        # 检查是否已有 stderr handler
        has_stderr = any(
            isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
            for h in root_logger.handlers
        )
        if not has_stderr:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            ))
            root_logger.addHandler(handler)
            root_logger.setLevel(logging.DEBUG)

    # --------------------------------------------------------
    # 工具注册
    # --------------------------------------------------------

    def register_tool(
        self,
        name: str,
        callable_func: Any,
        schema: dict[str, Any],
    ) -> None:
        """注册 MCP 工具

        接口签名：register_tool(name, callable_func, schema) -> None
        入参：
          - name: 工具名称（如 "query_knowledge_hub"）
          - callable_func: 工具执行函数
          - schema: 工具 schema（description, inputSchema）

        知识点：工具注册
          - 将工具名称映射到执行函数和 schema
          - ProtocolHandler 在 tools/list 时返回 schema
          - ProtocolHandler 在 tools/call 时路由到 callable
          - 面试考点："register_tool 和直接调用的区别？" → 注册后可动态发现（tools/list）
        """
        self._protocol.register_tool(name, callable_func, schema)
        logger.info("工具已注册: %s", name)

    # --------------------------------------------------------
    # 消息循环
    # --------------------------------------------------------

    def run(self) -> None:
        """阻塞式运行 MCP Server

        接口签名：run() -> None
        行为：从 stdin 逐行读取 JSON-RPC 请求，处理后将响应写入 stdout

        消息循环（面试考点）：
          1. 从 stdin 读取一行
          2. EOF → 退出循环
          3. 空行 → 跳过
          4. 解析并处理（ProtocolHandler）
          5. 将响应写入 stdout（一行一个 JSON）
          6. 继续循环

        知识点：行协议（Line Protocol）
          - 每条消息一行（以 \n 结尾）
          - 基于 Content-Length 的帧协议在生产环境更安全
          - 面试考点："行协议的局限？" → JSON 中不能包含换行符（但这不是问题因为 JSON 序列化不产生换行）
        """
        self._running = True
        logger.info("MCP Server 启动 (Stdio Transport)")

        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                response = self._protocol.handle_message(line)

                if response is not None:
                    # 写入 stdout 并立即 flush（确保消息发送）
                    sys.stdout.write(response + "\n")
                    sys.stdout.flush()

        except KeyboardInterrupt:
            logger.info("MCP Server 收到中断信号，退出")
        except Exception as e:
            logger.exception("MCP Server 异常退出: %s", e)
        finally:
            self._running = False
            logger.info("MCP Server 已停止")

    @property
    def is_running(self) -> bool:
        """Server 是否正在运行"""
        return self._running


# ============================================================
# 便捷函数：run_server
# ============================================================

def create_server() -> MCPServer:
    """创建 MCP Server 实例

    接口签名：create_server() -> MCPServer
    出参：MCPServer 实例

    知识点：工厂函数
      - 方便测试时创建 Server 实例
      - 也方便在 __main__ 中启动
    """
    return MCPServer()


def main() -> None:
    """CLI 入口 — 启动 MCP Server

    使用方式：
      python -m mcp_server.server

    知识点：模块运行入口
      - python -m 直接运行模块
      - 创建 Server 并进入消息循环
      - 实际工具注册在外部（由上层组装）
    """
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()

