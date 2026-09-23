"""
MCP Server 集成测试 — E1: Stdio Transport 约束 + initialize 验证

测试策略：
  - 使用 subprocess 方式启动 MCP Server
  - 通过 stdin 发送 JSON-RPC 请求
  - 验证 stdout 输出的 JSON-RPC 响应
  - 验证 stderr 有日志但 stdout 不被污染

测试分类（12 个）：
  - Server 初始化（3）
  - Stdio 约束验证（3）
  - JSON-RPC 协议测试（4）
  - 工具注册与查询（2）
"""

from __future__ import annotations

import json
import os
import pytest
import subprocess
import sys
from pathlib import Path

# ============================================================
# 辅助变量
# ============================================================

# 项目根目录和 src/ 目录
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"


# ============================================================
# 辅助函数
# ============================================================

def run_mcp_server(
    input_lines: list[str],
    timeout: float = 5.0,
) -> tuple[str, str, int]:
    """启动 MCP Server 子进程，发送输入并返回输出

    接口签名：run_mcp_server(input_lines, timeout) -> (stdout, stderr, returncode)
    入参：
      - input_lines: 要发送到 stdin 的 JSON-RPC 请求列表
      - timeout: 超时时间（秒）
    出参：(stdout 内容, stderr 内容, 进程返回码）
    """
    # 设置 PYTHONPATH 让子进程能找到 mcp_server 模块
    env = os.environ.copy()
    python_path = str(_SRC_DIR)
    if "PYTHONPATH" in env:
        python_path = python_path + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = python_path

    # 启动 MCP Server 子进程
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(_PROJECT_ROOT),
    )

    # 拼接输入（每行一个 JSON-RPC 请求）
    input_text = "\n".join(input_lines) + "\n"

    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        pytest.fail(f"MCP Server 超时（>{timeout}s）")

    return stdout.strip(), stderr.strip(), proc.returncode


def parse_jsonrpc_response(line: str) -> dict:
    """解析 JSON-RPC 响应行

    接口签名：parse_jsonrpc_response(line: str) -> dict
    入参：一行 JSON 字符串
    出参：解析后的 dict
    """
    return json.loads(line)


# ============================================================
# TestServerInitialization — Server 初始化测试
# ============================================================

class TestServerInitialization:
    """Server 初始化测试（3 个测试）

    知识点：MCP Server 启动时的初始化流程
      1. 创建 Server 实例
      2. 配置日志到 stderr
      3. 等待 stdin 输入
      4. 收到 initialize 请求后返回 serverInfo + capabilities
    """

    def test_initialize_returns_server_info(self) -> None:
        """initialize 请求返回正确的 serverInfo"""
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        })

        stdout, stderr, returncode = run_mcp_server([request])

        # stdout 应为一行 JSON 响应
        assert stdout, f"stdout 为空: stderr={stderr!r}"

        lines = stdout.split("\n")
        assert len(lines) >= 1

        response = parse_jsonrpc_response(lines[0])
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response

        result = response["result"]
        assert result["serverInfo"]["name"] == "modular-rag-mcp-server"
        assert "version" in result["serverInfo"]
        assert "capabilities" in result

    def test_initialize_has_stderr_logs(self) -> None:
        """initialize 后 stderr 有日志输出"""
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
        })

        stdout, stderr, returncode = run_mcp_server([request])

        # stderr 应包含日志（初始化信息）
        assert len(stderr) > 0

    def test_initialize_returns_capabilities(self) -> None:
        """initialize 返回 capabilities.tools"""
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 100,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
        })

        stdout, stderr, returncode = run_mcp_server([request])

        assert stdout, f"stdout 为空: stderr={stderr!r}"
        response = parse_jsonrpc_response(stdout.split("\n")[0])
        assert "tools" in response["result"]["capabilities"]


# ============================================================
# TestStdioConstraints — Stdio 约束验证
# ============================================================

class TestStdioConstraints:
    """Stdio Transport 约束验证（3 个测试）

    知识点：Stdio Transport 核心约束
      - stdout: 只输出 JSON-RPC 消息（有效的 JSON）
      - stderr: 所有日志
      - stdout 中不能有任何非 JSON 内容（包括日志、调试信息）
    """

    def test_stdout_only_valid_json(self) -> None:
        """stdout 的每一行都是有效的 JSON-RPC 消息"""
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
        })

        stdout, stderr, returncode = run_mcp_server([request])

        # stdout 的每一行都应该是有效的 JSON
        stdout_lines = [line for line in stdout.split("\n") if line.strip()]
        for line in stdout_lines:
            try:
                parsed = json.loads(line)
                assert parsed["jsonrpc"] == "2.0"
            except (json.JSONDecodeError, KeyError):
                pytest.fail(f"stdout 包含无效 JSON: {line!r}")

    def test_stdout_single_response(self) -> None:
        """一个请求只产生一个响应（一行 JSON）"""
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 42,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
        })

        stdout, stderr, returncode = run_mcp_server([request])

        # stdout 应该只有一行（一个响应）
        stdout_lines = [line for line in stdout.split("\n") if line.strip()]
        assert len(stdout_lines) == 1, f"期望 1 行响应，实际 {len(stdout_lines)} 行: {stdout_lines}"

    def test_stderr_contains_server_logs(self) -> None:
        """stderr 包含 Server 启动和停止日志"""
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
        })

        stdout, stderr, returncode = run_mcp_server([request])

        # stderr 应包含 Server 日志
        assert len(stderr) > 0


# ============================================================
# TestJSONRPCProtocol — JSON-RPC 协议测试
# ============================================================

class TestJSONRPCProtocol:
    """JSON-RPC 2.0 协议规范测试（4 个测试）

    知识点：JSON-RPC 2.0 错误码
      - -32700: Parse Error（JSON 解析失败）
      - -32600: Invalid Request（请求格式无效）
      - -32601: Method not found（方法不存在）
      - -32602: Invalid params（参数无效）
      - -32603: Internal error（内部错误）
    """

    def test_invalid_json_returns_parse_error(self) -> None:
        """无效 JSON 返回 -32700 Parse Error"""
        stdout, stderr, returncode = run_mcp_server(["this is not json"])

        assert stdout, f"stdout 为空: stderr={stderr!r}"
        response = parse_jsonrpc_response(stdout.split("\n")[0])
        assert "error" in response
        assert response["error"]["code"] == -32700

    def test_missing_method_returns_invalid_request(self) -> None:
        """缺少 method 返回 -32600 Invalid Request"""
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "params": {}})
        stdout, stderr, returncode = run_mcp_server([request])

        assert stdout, f"stdout 为空: stderr={stderr!r}"
        response = parse_jsonrpc_response(stdout.split("\n")[0])
        assert "error" in response
        assert response["error"]["code"] == -32600

    def test_unknown_method_returns_method_not_found(self) -> None:
        """未知方法返回 -32601 Method not found"""
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown/method", "params": {}})
        stdout, stderr, returncode = run_mcp_server([request])

        assert stdout, f"stdout 为空: stderr={stderr!r}"
        response = parse_jsonrpc_response(stdout.split("\n")[0])
        assert "error" in response
        assert response["error"]["code"] == -32601

    def test_invalid_jsonrpc_version_returns_error(self) -> None:
        """错误的 jsonrpc 版本返回 Invalid Request"""
        request = json.dumps({"jsonrpc": "1.0", "id": 1, "method": "initialize", "params": {}})
        stdout, stderr, returncode = run_mcp_server([request])

        assert stdout, f"stdout 为空: stderr={stderr!r}"
        response = parse_jsonrpc_response(stdout.split("\n")[0])
        assert "error" in response
        assert response["error"]["code"] == -32600


# ============================================================
# TestToolsRegistry — 工具注册与查询
# ============================================================

class TestToolsRegistry:
    """工具注册与查询测试（2 个测试）"""

    def test_tools_list_returns_empty_when_no_tools(self) -> None:
        """无工具注册时 tools/list 返回空列表"""
        # 先 initialize
        init_request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
        })

        # 再 list tools
        list_request = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })

        stdout, stderr, returncode = run_mcp_server([init_request, list_request])

        assert stdout, f"stdout 为空: stderr={stderr!r}"

        # 找到 id=2 的响应
        lines = [l for l in stdout.split("\n") if l.strip()]
        response = parse_jsonrpc_response(lines[-1])
        assert response["id"] == 2
        assert "result" in response
        assert response["result"]["tools"] == []

    def test_tools_list_after_initialize_succeeds(self) -> None:
        """initialize 后 tools/list 返回有效响应"""
        requests = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
            }),
            json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }),
        ]

        stdout, stderr, returncode = run_mcp_server(requests)

        assert stdout, f"stdout 为空: stderr={stderr!r}"
        lines = [l for l in stdout.split("\n") if l.strip()]
        # 应有两个响应
        assert len(lines) == 2
        last_response = parse_jsonrpc_response(lines[-1])
        assert last_response["id"] == 2
        assert "result" in last_response


# ============================================================
# TestQueryKnowledgeHub — query_knowledge_hub Tool 测试
# ============================================================

class TestQueryKnowledgeHub:
    """query_knowledge_hub Tool 测试（直接测试，不通过 subprocess）

    知识点：MCP Tool 单元测试
      - 直接测试 Tool 函数（而非通过 subprocess）
      - 使用 Mock HybridSearch 控制检索结果
      - 验证 MCP 响应格式正确
    """

    def test_tool_schema_has_required_fields(self) -> None:
        """TOOL_SCHEMA 包含必需字段"""
        from mcp_server.tools.query_knowledge_hub import TOOL_SCHEMA

        assert "description" in TOOL_SCHEMA
        assert "inputSchema" in TOOL_SCHEMA
        assert "properties" in TOOL_SCHEMA["inputSchema"]
        assert "query" in TOOL_SCHEMA["inputSchema"]["properties"]
        assert "top_k" in TOOL_SCHEMA["inputSchema"]["properties"]

    def test_tool_schema_query_is_required(self) -> None:
        """query 是必需参数"""
        from mcp_server.tools.query_knowledge_hub import TOOL_SCHEMA

        assert "query" in TOOL_SCHEMA["inputSchema"].get("required", [])

    def test_tool_schema_has_collection_optional(self) -> None:
        """collection 是可选参数"""
        from mcp_server.tools.query_knowledge_hub import TOOL_SCHEMA

        assert "collection" in TOOL_SCHEMA["inputSchema"]["properties"]
        # collection 不在 required 列表中
        assert "collection" not in TOOL_SCHEMA["inputSchema"].get("required", [])

