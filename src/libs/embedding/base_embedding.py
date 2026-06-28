# Embedding 抽象基类
# 知识点：Embedding 是将文本转为高维向量的过程
#   - embed(texts) -> list[list[float]]: 批量文本转向量
#   - 同一语义空间的向量可以用余弦相似度比较
#   - 这是 Dense Retrieval 的基础
