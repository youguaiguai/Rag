# VectorStore 抽象基类
# 知识点：VectorStore 是向量数据库的统一接口
#   - add(ids, embeddings, metadatas): 添加向量
#   - query(embedding, top_k): 相似度检索
#   - delete(ids): 删除向量
#   - 不同后端（Chroma/Qdrant/Pinecone）只需实现此接口
