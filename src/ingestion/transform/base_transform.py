# Transform 抽象基类
# 知识点：Transform 是 Pipeline 中的"增强"环节
#   - 原子化：每个 Transform 只做一件事
#   - 幂等性：重复执行结果不变
#   - 降级安全：失败不阻塞 Pipeline，只记录警告
