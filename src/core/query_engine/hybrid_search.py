# 混合检索引擎 — Dense + Sparse + RRF Fusion
# 知识点：Hybrid Search 是 RAG 检索的核心策略
#   - Dense Retrieval: 语义向量检索，解决同义词问题（如"机器学习" ≈ "ML"）
#   - Sparse Retrieval (BM25): 关键词检索，解决专有名词精确匹配
#   - RRF Fusion: 两种结果的排名融合算法
#   - 两段式架构：粗排（Hybrid Search）→ 精排（Reranker）
