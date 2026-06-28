# MCP Server 入口
# 知识点：MCP (Model Context Protocol) 是 Anthropic 定义的 AI 工具调用协议
# 通过 Stdio Transport 通信：stdin 接收请求，stdout 返回响应
# 所有日志必须输出到 stderr，不能污染 stdout（否则会破坏 JSON-RPC 协议）
