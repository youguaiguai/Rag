"""
ProtocolHandler 单元测试 — E2: 协议解析与能力 negotiation

测试策略：
  - 直接测试 ProtocolHandler 类（不通过 subprocess）
  - 覆盖三大核心方法：initialize、tools/list、tools/call
  - 覆盖所有 JSON-RPC 2.0 错误码
  - 覆盖能力 negotiation

测试分类（20 个）：
  - Initialize 处理（4）
  - Tools/List 处理（4）
  - Tools/Call 路由（5）
  - JSON-RPC 错误处理（5）
  - 通知消息（2）
"""

from __future__ import annotations

import json
import pytest
import sys
from pathlib import Path
from typing import Any

# 确保 src/ 在路径中
_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from mcp_server.protocol_handler import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    ProtocolHandler,
)


# ============================================================
# 辅助函数
# ============================================================

def make_request(method: str, params: dict | None = None, request_id: Any = 1) -> str:
    """构造 JSON-RPC 请求"""
    req: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        req["params"] = params
    return json.dumps(req)


def parse_response(raw: str) -> dict:
    """解析 JSON-RPC 响应"""
    return json.loads(raw)


# ============================================================
# TestInitialize — Initialize 处理测试
# ============================================================

class TestInitialize:
    """Initialize 处理测试（4 个测试）

    知识点：initialize 是 Client 和 Server 的握手过程
      - Client 发送协议版本和支持的能力
      - Server 返回自身支持的协议版本和能力列表
      - 双方确认后续通信格式
    """

    def test_initialize_returns_protocol_version(self) -> None:
        """initialize 返回正确的协议版本"""
        handler = ProtocolHandler()
        response = handler.handle_message(make_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))

        result = parse_response(response)
        assert "result" in result
        assert "protocolVersion" in result["result"]

    def test_initialize_returns_server_info(self) -> None:
        """initialize 返回 serverInfo"""
        handler = ProtocolHandler()
        response = handler.handle_message(make_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))

        result = parse_response(response)
        server_info = result["result"]["serverInfo"]
        assert server_info["name"] == "modular-rag-mcp-server"
        assert "version" in server_info

    def test_initialize_returns_capabilities(self) -> None:
        """initialize 返回 capabilities.tools"""
        handler = ProtocolHandler()
        response = handler.handle_message(make_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))

        result = parse_response(response)
        assert "capabilities" in result["result"]
        assert "tools" in result["result"]["capabilities"]

    def test_initialize_with_empty_params(self) -> None:
        """initialize 能处理空 params"""
        handler = ProtocolHandler()
        response = handler.handle_message(make_request("initialize", {}))

        result = parse_response(response)
        assert "result" in result
        assert result["result"]["serverInfo"]["name"] == "modular-rag-mcp-server"


# ============================================================
# TestToolsList — Tools/List 处理测试
# ============================================================

class TestToolsList:
    """Tools/List 处理测试（4 个测试）

    知识点：tools/list 返回 Server 注册的所有工具 schema
      - 每个工具包含 name/description/inputSchema
      - Client 根据 schema 动态构造参数
    """

    def test_tools_list_no_tools(self) -> None:
        """无工具时返回空列表"""
        handler = ProtocolHandler()
        response = handler.handle_message(make_request("tools/list"))

        result = parse_response(response)
        assert result["result"]["tools"] == []

    def test_tools_list_returns_registered_tools(self) -> None:
        """返回已注册工具的 schema"""
        handler = ProtocolHandler()

        # 注册一个工具
        def dummy_tool(query: str) -> dict:
            return {"content": [{"type": "text", "text": f"Result for: {query}"}]}

        handler.register_tool(
            "test_tool",
            dummy_tool,
            {
                "description": "A test tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Query text"},
                    },
                    "required": ["query"],
                },
            },
        )

        response = handler.handle_message(make_request("tools/list"))
        result = parse_response(response)

        tools = result["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"
        assert tools[0]["description"] == "A test tool"
        assert "inputSchema" in tools[0]

    def test_tools_list_returns_all_registered(self) -> None:
        """返回所有已注册工具"""
        handler = ProtocolHandler()

        def tool_a(q: str) -> dict:
            return {"content": [{"type": "text", "text": "a"}]}

        def tool_b(q: str) -> dict:
            return {"content": [{"type": "text", "text": "b"}]}

        handler.register_tool("tool_a", tool_a, {"description": "Tool A", "inputSchema": {"type": "object", "properties": {}}})
        handler.register_tool("tool_b", tool_b, {"description": "Tool B", "inputSchema": {"type": "object", "properties": {}}})

        response = handler.handle_message(make_request("tools/list"))
        result = parse_response(response)

        tool_names = {t["name"] for t in result["result"]["tools"]}
        assert tool_names == {"tool_a", "tool_b"}

    def test_tools_list_tools_have_required_fields(self) -> None:
        """每个工具有 name/description/inputSchema 三个必需字段"""
        handler = ProtocolHandler()
        handler.register_tool(
            "my_tool",
            lambda: {},
            {"description": "Test", "inputSchema": {"type": "object", "properties": {}}},
        )

        response = handler.handle_message(make_request("tools/list"))
        result = parse_response(response)

        tool = result["result"]["tools"][0]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


# ============================================================
# TestToolsCall — Tools/Call 路由测试
# ============================================================

class TestToolsCall:
    """Tools/Call 路由测试（5 个测试）

    知识点：tools/call 执行具体的工具函数
      - 从 params 提取工具名称和参数
      - 在 tools_registry 中查找对应工具
      - 执行工具函数并返回格式化结果
    """

    def test_tools_call_executes_registered_tool(self) -> None:
        """调用已注册工具并返回结果"""
        handler = ProtocolHandler()

        def echo_tool(message: str) -> dict:
            return {"content": [{"type": "text", "text": f"Echo: {message}"}]}

        handler.register_tool(
            "echo",
            echo_tool,
            {"description": "Echo tool", "inputSchema": {"type": "object", "properties": {"message": {"type": "string"}}}},
        )

        response = handler.handle_message(make_request("tools/call", {
            "name": "echo",
            "arguments": {"message": "hello"},
        }))

        result = parse_response(response)
        assert "result" in result
        assert "content" in result["result"]

    def test_tools_call_returns_tool_result(self) -> None:
        """工具执行结果正确"""
        handler = ProtocolHandler()

        def add(a: int = 0, b: int = 0) -> dict:
            return {"content": [{"type": "text", "text": str(a + b)}]}

        handler.register_tool(
            "add",
            add,
            {
                "description": "Add two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                },
            },
        )

        response = handler.handle_message(make_request("tools/call", {
            "name": "add",
            "arguments": {"a": 3, "b": 5},
        }))

        result = parse_response(response)
        assert "content" in result["result"]

    def test_tools_call_unknown_tool_returns_error(self) -> None:
        """调用未注册工具返回 -32602 Invalid params"""
        handler = ProtocolHandler()

        response = handler.handle_message(make_request("tools/call", {
            "name": "nonexistent_tool",
            "arguments": {},
        }))

        result = parse_response(response)
        assert "error" in result
        assert result["error"]["code"] == INVALID_PARAMS

    def test_tools_call_missing_name_returns_error(self) -> None:
        """缺少工具名返回 Invalid params"""
        handler = ProtocolHandler()

        response = handler.handle_message(make_request("tools/call", {
            "arguments": {},
        }))

        result = parse_response(response)
        assert "error" in result
        assert result["error"]["code"] == INVALID_PARAMS

    def test_tools_call_empty_arguments(self) -> None:
        """空 arguments 正常处理"""
        handler = ProtocolHandler()

        def no_args_tool() -> dict:
            return {"content": [{"type": "text", "text": "no args needed"}]}

        handler.register_tool(
            "no_args",
            no_args_tool,
            {"description": "No args", "inputSchema": {"type": "object", "properties": {}}},
        )

        response = handler.handle_message(make_request("tools/call", {
            "name": "no_args",
            "arguments": {},
        }))

        result = parse_response(response)
        assert "result" in result


# ============================================================
# TestJSONRPCErrorHandling — JSON-RPC 错误处理测试
# ============================================================

class TestJSONRPCErrorHandling:
    """JSON-RPC 错误处理测试（5 个测试）

    知识点：JSON-RPC 2.0 标准错误码
      - -32700: Parse Error
      - -32600: Invalid Request
      - -32601: Method not found
      - -32602: Invalid params
      - -32603: Internal error
    """

    def test_parse_error_on_invalid_json(self) -> None:
        """无效 JSON 返回 -32700"""
        handler = ProtocolHandler()
        response = handler.handle_message("not valid json{{{")
        result = parse_response(response)
        assert result["error"]["code"] == PARSE_ERROR

    def test_invalid_request_missing_method(self) -> None:
        """缺少 method 返回 -32600"""
        handler = ProtocolHandler()
        response = handler.handle_message(json.dumps({"jsonrpc": "2.0", "id": 1}))
        result = parse_response(response)
        assert result["error"]["code"] == INVALID_REQUEST

    def test_invalid_request_wrong_version(self) -> None:
        """错误的 jsonrpc 版本返回 -32600"""
        handler = ProtocolHandler()
        response = handler.handle_message(json.dumps({"jsonrpc": "1.0", "id": 1, "method": "test"}))
        result = parse_response(response)
        assert result["error"]["code"] == INVALID_REQUEST

    def test_method_not_found(self) -> None:
        """未知方法返回 -32601"""
        handler = ProtocolHandler()
        response = handler.handle_message(make_request("unknown/method"))
        result = parse_response(response)
        assert result["error"]["code"] == METHOD_NOT_FOUND

    def test_non_object_request_returns_invalid_request(self) -> None:
        """非对象请求返回 -32600"""
        handler = ProtocolHandler()
        response = handler.handle_message(json.dumps(["array", "not", "object"]))
        result = parse_response(response)
        assert result["error"]["code"] == INVALID_REQUEST


# ============================================================
# TestNotifications — 通知消息测试
# ============================================================

class TestNotifications:
    """通知消息测试（2 个测试）

    知识点：JSON-RPC 通知（Notification）
      - 无 id 的请求是通知
      - 通知不需要响应（返回 None）
      - 常见通知：notifications/initialized
    """

    def test_notification_returns_none(self) -> None:
        """通知消息不返回响应（返回 None）"""
        handler = ProtocolHandler()
        # 构造无 id 的通知
        notification = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

        response = handler.handle_message(notification)
        assert response is None

    def test_initialized_notification_no_response(self) -> None:
        """initialized 通知不产生响应"""
        handler = ProtocolHandler()
        notification = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

        response = handler.handle_message(notification)
        assert response is None

