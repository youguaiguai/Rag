notes = """

---

## 38. E1：MCP Server 入口与 Stdio 约束

### 38.1 设计目标

实现 MCP Server 的 Protocol Handler 和 Server 入口，满足 E1 验收标准：
- stdout 只输出 MCP 消息（有效的 JSON-RPC），日志输出到 stderr
- 能完成 initialize 流程
- 支持 tools/list 和 tools/call 方法路由

### 38.2 修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/mcp_server/__init__.py` | 创建 | 包初始化文件 |
| `src/mcp_server/protocol_handler.py` | 实现 | JSON-RPC 2.0 协议处理器 |
| `src/mcp_server/server.py` | 实现 | MCP Server 入口 + Stdio Transport |
| `tests/integration/test_mcp_server.py` | 创建 | 12 个集成测试 |

### 38.3 架构设计

#### Protocol Handler (JSON-RPC 2.0)

```
handle_message(raw: str) -> str | None
    ├── -32700 Parse Error: JSON 解析失败
    ├── -32600 Invalid Request: 无效请求格式
    ├── 路由方法：
    │   ├── initialize → serverInfo + capabilities
    │   ├── tools/list → 工具 schema 列表
    │   └── tools/call → 执行工具并返回结果
    ├── -32601 Method not found: 未知方法
    ├── -32602 Invalid params: 参数错误
    └── -32603 Internal error: 内部异常（不泄露堆栈）
```

#### MCPServer (Stdio Transport)

```
MCPServer.run() → None
    ├── for line in stdin:
    │   ├── ProtocolHandler.handle_message(line)
    │   ├── 有响应 → sys.stdout.write(response + "\\n") + flush
    │   └── 无响应（通知消息）→ 跳过
    └── stdin EOF → 优雅退出

约束：
    ├── stdout: 只输出 JSON-RPC 消息
    └── stderr: 所有日志（通过 logger → stderr handler）
```

### 38.4 E1 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| Server 初始化 | 3 | serverInfo、stderr 日志、capabilities |
| Stdio 约束验证 | 3 | stdout 有效 JSON、单响应行、stderr 有日志 |
| JSON-RPC 协议 | 4 | Parse Error、Invalid Request、Method not found、无效版本 |
| 工具注册与查询 | 2 | tools/list 返回空列表、tools/list 正常返回 |
| **E1 合计** | **12** | 12 passed |

### 38.5 E1 面试问答

| 问题 | 回答 |
|------|------|
| "Stdio Transport 约束是什么？" | stdout 只输出 JSON-RPC 消息，日志全部走 stderr |
| "为什么日志不能输出到 stdout？" | 会破坏 JSON-RPC 协议解析（一行必须是一个完整 JSON） |
| "JSON-RPC 错误码有哪些？" | -32700 Parse Error、-32600 Invalid Request、-32601 Method not found、-32602 Invalid params、-32603 Internal error |
| "怎么测试 stdout 不被污染？" | 逐行验证 stdout 是有效的 JSON-RPC 消息 |
| "如何实现 graceful shutdown？" | stdin EOF 时退出循环 |
| "ProtocolHandler 和 MCPServer 的关系？" | Server 做 I/O，ProtocolHandler 做协议解析，解耦设计 |
"""

with open("Notes.md", "a") as f:
    f.write(notes)

print("E1 notes appended")

