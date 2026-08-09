"""
VectorStore 模块 — 可插拔的向量数据库抽象层

导出：
  - BaseVectorStore: 抽象基类，所有向量数据库的统一接口
  - VectorStoreError: 操作异常
  - VectorRecord: upsert 输入数据类型
  - QueryResult: query 输出数据类型
  - VectorStoreFactory: 工厂类，根据配置创建对应实现
  - FakeVectorStore: 测试桩，纯内存存储
"""

__all__ = [
    "BaseVectorStore",
    "VectorStoreError",
    "VectorRecord",
    "QueryResult",
    "VectorStoreFactory",
    "FakeVectorStore",
]

