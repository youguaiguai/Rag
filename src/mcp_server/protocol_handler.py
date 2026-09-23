"""
JSON-RPC 2.0 协议处理器 — MCP 通信协议解析与路由

知识点：MCP 协议基于 JSON-RPC 2.0，核心方法：
  - initialize: 能力协商（Client 和 Server 交换支持的能力）
  - tools/list: 返回所有可用工具的 Schema
  - tools/call: 执行具体工具并返回结果

JSON-RPC 2.0 规范（面试考点）：
  - 请求格式：{"jsonrpc": "2.0", "id": <string|number>, "method": <string>, "params": <object>}
  - 响应格式：{"jsonrpc": "2.0", "id": <same as request>, "result": <any>}
  - 错误格式：{"jsonrpc": "2.0", "id": <same as request>, "error": {"code": <int>, "message": <string>}}

错误码规范：
  - -32700 Parse Error: JSON 解析失败
  - -32600 Invalid Request: 无效请求格式
  - -32601 Method not found: 方法不存在
  - -32602 Invalid params: 参数无效
  - -32603 Internal error: 内部错误

Stdio Transport 约束（面试考点）：
  - stdout: 只输出 JSON-RPC 消息（一行一个 JSON）
  - stderr: 所有日志输出到 stderr
  - 面试考点："为什么日志不能输出到 stdout？" → 会破坏 JSON-RPC 协议解析

接口签名：
  ProtocolHandler(tools_registry: dict)  # tool_name → { callable, schema }
  handle_message(raw: str) -> str | None  # 入参：一行 JSON；出参：一行 JSON 或 None
  handle_initialize(params) -> dict
  handle_tools_list() -> list[dict]
  handle_tools_call(name, arguments) -> dict
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# JSON-RPC 错误码常量
# ============================================================

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ProtocolHandler:
    """JSON-RPC 2.0 协议处理器 — 解析、路由、错误处理

    知识点：ProtocolHandler 的设计原则
      - 只负责协议解析和方法路由，不实现具体工具逻辑
      - 所有工具通过 tools_registry 注册，支持动态扩展
      - 异常转换为标准 JSON-RPC 错误，不泄露内部堆栈
      - 面试考点："为什么要把错误码标准化？" → 客户端能根据错误码做不同处理

    接口签名：
      ProtocolHandler(tools_registry: dict)
      handle_message(raw: str) -> str | None
    """

    def __init__(self, tools_registry: dict[str, dict[str, Any]] | None = None) -> None:
        """初始化 ProtocolHandler

        接口签名：ProtocolHandler(tools_registry=None)
        入参：
          - tools_registry: 工具注册表
            {tool_name: {"callable": callable, "schema": {...}}}
        """
        self._tools = tools_registry or {}
        self._initialized = False

    # --------------------------------------------------------
    # 主入口：handle_message
    # --------------------------------------------------------

    def handle_message(self, raw: str) -> str | None:
        """处理一条 JSON-RPC 请求消息

        接口签名：handle_message(raw: str) -> str | None
        入参：raw — 一行 JSON 字符串
        出参：JSON 响应字符串，或 None（通知消息无需响应）

        处理流程：
          1. 解析 JSON（失败 → Parse Error -32700）
          2. 验证请求格式（失败 → Invalid Request -32600）
          3. 路由到对应方法（失败 → Method not found -32601）
          4. 执行方法并捕获异常（失败 → Internal error -32603）
        """
        # 1. 解析 JSON
        try:
            request = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("JSON 解析失败: %s", e)
            return self._error_response(None, PARSE_ERROR, "Parse error: invalid JSON")

        # 2. 验证请求格式
        if not isinstance(request, dict):
            return self._error_response(None, INVALID_REQUEST, "Invalid Request: not an object")

        if request.get("jsonrpc") != "2.0":
            return self._error_response(
                request.get("id"), INVALID_REQUEST,
                "Invalid Request: jsonrpc must be '2.0'",
            )

        if "method" not in request or not isinstance(request["method"], str):
            return self._error_response(
                request.get("id"), INVALID_REQUEST,
                "Invalid Request: missing or invalid 'method'",
            )

        # 3. 提取请求字段
        request_id = request.get("id")
        method = request["method"]
        params = request.get("params", {})

        # 通知消息（无 id）→ 不返回响应
        if request_id is None:
            logger.debug("收到通知消息: %s (无响应)", method)
            return None

        # 4. 路由到对应方法
        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "notifications/initialized":
                # 通知：Client 确认初始化完成，无需响应
                self._initialized = True
                logger.debug("Client 确认初始化完成")
                return None
            elif method == "tools/list":
                result = self._handle_tools_list(params)
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            else:
                return self._error_response(
                    request_id, METHOD_NOT_FOUND,
                    f"Method not found: '{method}'",
                )

            return self._success_response(request_id, result)

        except json.JSONDecodeError as e:
            return self._error_response(
                request_id, PARSE_ERROR, f"Parse error: {e}",
            )
        except ValueError as e:
            return self._error_response(
                request_id, INVALID_PARAMS, f"Invalid params: {e}",
            )
        except Exception as e:
            logger.exception("处理 %s 时发生内部错误", method)
            # 不泄露堆栈信息，只返回通用错误
            return self._error_response(
                request_id, INTERNAL_ERROR,
                f"Internal error: {type(e).__name__}",
            )

    # --------------------------------------------------------
    # 方法处理器
    # --------------------------------------------------------

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 initialize 请求

        接口签名：_handle_initialize(params: dict) -> dict
        入参：Client 发送的初始化参数
        出参：Server 能力信息（serverInfo + capabilities）

        知识点：能力协商
          - Client 发送协议版本和支持的能力
          - Server 返回自身支持的协议版本和能力列表
          - 双方确认后续通信格式
          - 面试考点："为什么需要 initialize？" → 版本兼容性检查 + 能力协商
        """
        # 记录 Client 信息（如果提供）
        client_info = params.get("clientInfo", {})
        client_name = client_info.get("name", "unknown")

        logger.info("初始化请求 from client: %s (version: %s)",
                    client_name, client_info.get("version", "unknown"))

        self._initialized = True

        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "modular-rag-mcp-server",
                "version": "0.1.0",
            },
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
        }

    def _handle_tools_list(self, _params: dict[str, Any]) -> dict[str, Any]:
        """处理 tools/list 请求

        接口签名：_handle_tools_list(params: dict) -> dict
        入参：通常为空
        出参：已注册工具的 schema 列表

        知识点：Tool Schema
          - 每个工具暴露 name/description/inputSchema
          - Client 根据 schema 构造参数
          - 面试考点："为什么用 JSON Schema 描述参数？" → 客户端可以动态校验参数
        """
        tools = []
        for name, tool_info in self._tools.items():
            schema = tool_info.get("schema", {})
            tools.append({
                "name": name,
                "description": schema.get("description", ""),
                "inputSchema": schema.get("inputSchema", {
                    "type": "object",
                    "properties": {},
                }),
            })

        return {"tools": tools}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 tools/call 请求

        接口签名：_handle_tools_call(params: dict) -> dict
        入参：{"name": str, "arguments": dict}
        出参：{"content": list[dict], "structuredContent": dict}

        知识点：Tool 执行路由
          - 从 params 提取工具名称和参数
          - 在 tools_registry 中查找对应工具
          - 执行工具函数并返回格式化结果
          - 面试考点："为什么用注册表模式？" → 解耦工具实现和协议层

        错误处理：
          - 工具不存在 → Invalid params -32602
          - 工具执行异常 → Internal error -32603（不泄露堆栈）
        """
        tool_name = params.get("name")
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError("Missing or invalid 'name' parameter")

        arguments = params.get("arguments", {})

        # 查找工具
        tool_info = self._tools.get(tool_name)
        if tool_info is None:
            raise ValueError(f"Tool not found: '{tool_name}'")

        # 执行工具
        callable_func = tool_info["callable"]
        logger.debug("执行工具: %s, 参数: %s", tool_name, list(arguments.keys()))

        result = callable_func(**arguments)

        # 返回 MCP 响应格式
        return result

    # --------------------------------------------------------
    # 工具注册
    # --------------------------------------------------------

    def register_tool(self, name: str, callable_func: Any, schema: dict[str, Any]) -> None:
        """注册工具

        接口签名：register_tool(name, callable_func, schema) -> None
        入参：
          - name: 工具名称
          - callable_func: 可调用函数
          - schema: 工具 schema (description, inputSchema)

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增工具不改协议层代码
          - 对修改封闭：handle_message 方法不需要修改
          - 面试考点："如何新增一个 Tool？" → 实现函数 + register_tool
        """
        self._tools[name] = {
            "callable": callable_func,
            "schema": schema,
        }
        logger.debug("工具已注册: %s", name)

    # --------------------------------------------------------
    # 响应构造（内部方法）
    # --------------------------------------------------------

    def _success_response(self, request_id: Any, result: Any) -> str:
        """构造成功响应

        接口签名：_success_response(request_id, result) -> str
        出参：JSON-RPC 2.0 响应字符串
        """
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
        return json.dumps(response, ensure_ascii=False)

    def _error_response(self, request_id: Any | None, code: int, message: str) -> str:
        """构造错误响应

        接口签名：_error_response(request_id, code, message) -> str
        入参：
          - request_id: 请求 ID（可能为 None，如果解析失败）
          - code: JSON-RPC 错误码
          - message: 错误描述
        出参：JSON-RPC 2.0 错误响应字符串

        知识点：错误响应格式
          - 必须包含 jsonrpc/id/error 三个字段
          - error 内部包含 code + message
          - 面试考点："错误响应和成功响应的区别？" → 用 error 替代 result
        """
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        return json.dumps(response, ensure_ascii=False)

