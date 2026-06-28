# 核心数据类型/契约 — 全链路复用
# 知识点：types.py 是整个系统的"数据契约中心"
#   - Document: 文档对象（text + metadata）
#   - Chunk: 文档分块（Document 的子集，带位置信息）
#   - ChunkRecord: 带向量的 Chunk（用于存储和检索）
#   - 所有模块（ingestion/retrieval/mcp）共享同一套数据定义
#   - 好处：避免不同模块间的格式转换，保证数据一致性
