# 文档生命周期管理 — list / delete / stats
# 知识点：DocumentManager 跨 4 个存储协调删除
#   - ChromaStore: 向量数据
#   - BM25Indexer: 倒排索引
#   - ImageStorage: 图片文件 + SQLite 索引
#   - FileIntegrity: 文件哈希记录
#   - 删除一个文档时，4 个存储必须同步清理，否则出现"幽灵数据"
