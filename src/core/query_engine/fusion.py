# 结果融合 — RRF (Reciprocal Rank Fusion) 算法
# 知识点：RRF 的核心思想 — 不依赖分数的绝对值，只看排名
#   - 公式：Score(d) = Σ 1/(k + rank_i(d))  （k 是平滑常数，通常 60）
#   - 优势：Dense 和 Sparse 的分数量纲不同（余弦相似度 vs BM25 分数），
#     直接加权融合不可行，RRF 通过排名归一化解决了这个问题
