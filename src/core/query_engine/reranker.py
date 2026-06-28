# 重排序模块 — CrossEncoder / LLM Rerank / None 回退
# 知识点：Reranker 是"精排"阶段
#   - CrossEncoder: 双塔模型（Bi-Encoder）用于粗排，CrossEncoder 用于精排
#   - CrossEncoder 同时编码 query 和 doc，能捕捉更细粒度的语义关系
#   - 代价：速度慢（每个 query-doc 对都要单独编码），所以只对 Top-K 候选精排
