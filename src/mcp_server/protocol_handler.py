# JSON-RPC 2.0 协议处理器
# 知识点：MCP 协议基于 JSON-RPC 2.0，核心方法：
#   - initialize: 能力协商（Client 和 Server 交换支持的能力）
#   - tools/list: 返回所有可用工具的 Schema
#   - tools/call: 执行具体工具并返回结果
