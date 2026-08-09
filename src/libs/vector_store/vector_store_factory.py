"""
VectorStore 工厂 — 根据配置创建对应的 VectorStore 实例

知识点：
  - 工厂模式 (Factory Pattern)：将"创建哪个实现"的决策从业务代码中解耦
  - 核心方法：VectorStoreFactory.create(settings) -> BaseVectorStore
  - 配置驱动：settings.vector_store.backend 决定创建哪个 VectorStore 实例
  - 好处：切换向量数据库只改配置，不改代码

工厂路由逻辑：
  backend="chroma" → ChromaStore（B7.6 实现，嵌入式向量数据库）
  backend="qdrant" → QdrantStore（未来实现，需 Docker 部署）
  backend="fake"   → FakeVectorStore（测试桩，纯内存存储）

当前阶段（B4）：
  - 只实现 FakeVectorStore（测试桩），验证工厂路由逻辑和接口契约
  - ChromaStore 在 B7.6 阶段实现（需要 chromadb 包）
  - 面试考点："为什么先用 Fake 实现？" → 隔离测试 + 不依赖外部数据库

接口签名：
  VectorStoreFactory.create(settings: VectorStoreSettings) -> BaseVectorStore
    入参：VectorStore 配置对象
    出参：BaseVectorStore 子类实例
    异常：VectorStoreError — backend 不支持 / 依赖缺失
"""

from __future__ import annotations

import math
from typing import Any

from core.settings import VectorStoreSettings
from libs.vector_store.base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)


# ============================================================
# FakeVectorStore — 测试桩
# ============================================================

class FakeVectorStore(BaseVectorStore):
    """Fake VectorStore 实现 — 测试专用，纯内存存储

    知识点：测试桩 (Test Stub / Test Double)
      - 目的：隔离测试，不依赖 ChromaDB 等外部数据库
      - 行为：用 dict 内存存储，cosine similarity 纯 Python 计算
      - 面试考点："什么是测试桩？" → 替代真实依赖的可控实现

    存储结构：
      self._store: dict[str, VectorRecord]
      key = record.id, value = VectorRecord（包含 embedding、text、metadata）

    查询算法：
      - 对所有存储的向量计算与查询向量的 cosine similarity
      - 按 score 降序排列，取 top_k 条
      - 支持 metadata 过滤（精确匹配 filter 中的所有 key-value 对）

    使用场景：
      - 契约测试：验证 upsert/query/delete/get_by_ids 的输入输出 shape
      - 集成测试：在完整 Pipeline 中使用 FakeVectorStore 替代真实数据库
      - 回归测试：纯内存操作，速度快，确定性强
    """

    def __init__(self, settings: VectorStoreSettings) -> None:
        """初始化 FakeVectorStore

        接口签名：FakeVectorStore(settings: VectorStoreSettings)
        入参：
          - settings: VectorStore 配置（包含 backend、persist_path 等）
        """
        self._backend_name = "fake"
        self._store: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        """批量写入/更新向量记录（幂等）

        知识点：幂等 upsert 的实现
          - 用 dict 存储，key = record.id
          - 相同 id 的记录直接覆盖，不产生重复
          - 这就是 "upsert" = "update" + "insert" 的本质
        """
        for record in records:
            self._store[record.id] = record

    def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[QueryResult]:
        """向量相似度检索（cosine similarity）

        知识点：cosine similarity 的纯 Python 实现
          - cos(A, B) = (A · B) / (||A|| * ||B||)
          - A · B = sum(a_i * b_i)  — 点积
          - ||A|| = sqrt(sum(a_i^2)) — 向量模长
          - 值域 [-1, 1]，越接近 1 越相似

        metadata 过滤逻辑：
          - filters 中的每个 key-value 对都必须在 record.metadata 中精确匹配
          - 相当于 AND 逻辑：{"source": "doc.pdf", "page": 1} → source AND page 都匹配
        """
        # 1. 过滤符合条件的记录
        candidates: list[tuple[float, VectorRecord]] = []
        for record in self._store.values():
            # metadata 过滤
            if filters:
                match = all(
                    record.metadata.get(k) == v
                    for k, v in filters.items()
                )
                if not match:
                    continue

            # 2. 计算 cosine similarity
            score = self._cosine_similarity(vector, record.embedding)
            candidates.append((score, record))

        # 3. 按 score 降序排列，取 top_k
        candidates.sort(key=lambda x: x[0], reverse=True)
        results = [
            QueryResult(
                id=record.id,
                score=score,
                text=record.text,
                metadata=record.metadata,
            )
            for score, record in candidates[:top_k]
        ]

        return results

    def delete(self, ids: list[str]) -> int:
        """按 ID 删除记录"""
        deleted = 0
        for id_ in ids:
            if id_ in self._store:
                del self._store[id_]
                deleted += 1
        return deleted

    def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """按 ID 批量获取记录（不含向量）"""
        results = []
        for id_ in ids:
            record = self._store.get(id_)
            if record is not None:
                results.append({
                    "id": record.id,
                    "text": record.text,
                    "metadata": record.metadata,
                })
        return results

    def delete_by_metadata(self, filter: dict[str, Any]) -> int:
        """按 metadata 条件批量删除记录"""
        to_delete = []
        for id_, record in self._store.items():
            if all(record.metadata.get(k) == v for k, v in filter.items()):
                to_delete.append(id_)

        for id_ in to_delete:
            del self._store[id_]

        return len(to_delete)

    @property
    def backend_name(self) -> str:
        """返回后端名称"""
        return self._backend_name

    @property
    def count(self) -> int:
        """返回当前存储的记录数（测试辅助属性）"""
        return len(self._store)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算两个向量的余弦相似度

        知识点：cosine similarity 公式
          cos(A, B) = (A · B) / (||A|| * ||B||)
          - 点积：A · B = sum(a_i * b_i)
          - 模长：||A|| = sqrt(sum(a_i^2))
          - 值域 [-1, 1]，越接近 1 越相似
          - 面试考点："为什么用 cosine 而非欧氏距离？" → 不受向量长度影响，只关注方向

        边界处理：
          - 维度不匹配 → 返回 0.0（不相似）
          - 零向量 → 返回 0.0（避免除以零）
        """
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)


# ============================================================
# VectorStore 工厂
# ============================================================

class VectorStoreFactory:
    """VectorStore 工厂 — 根据 settings.vector_store.backend 创建对应实例

    接口签名：
      VectorStoreFactory.create(settings: VectorStoreSettings) -> BaseVectorStore

    知识点：工厂模式的三种实现方式
      1. 简单工厂（本项目采用）：一个 create 方法 + 映射表
      2. 工厂方法：每个产品一个工厂类（过度设计）
      3. 抽象工厂：一组相关产品的工厂（本项目不需要）

    为什么选简单工厂？
      - 向量数据库后端数量有限（2-3 个），映射表够用
      - 与 LLMFactory / EmbeddingFactory / SplitterFactory 保持一致
    """

    # Backend → 实现类的映射表
    _BACKENDS: dict[str, type[BaseVectorStore]] = {
        "fake": FakeVectorStore,
    }

    @classmethod
    def create(cls, settings: VectorStoreSettings) -> BaseVectorStore:
        """根据配置创建 VectorStore 实例

        接口签名：VectorStoreFactory.create(settings: VectorStoreSettings) -> BaseVectorStore
        入参：VectorStore 配置对象（包含 backend、persist_path 等）
        出参：BaseVectorStore 子类实例
        异常：VectorStoreError — backend 不支持

        面试考点：
          "工厂模式的好处？" → 改配置不改代码 + 上层只依赖接口
          "新增后端需要改什么？" → 实现 BaseVectorStore + 在 _BACKENDS 注册
        """
        backend = settings.backend.lower().strip()

        if backend not in cls._BACKENDS:
            supported = ", ".join(sorted(cls._BACKENDS.keys()))
            raise VectorStoreError(
                f"不支持的 VectorStore backend: '{backend}'。"
                f"当前支持: [{supported}]"
            )

        store_class = cls._BACKENDS[backend]
        return store_class(settings)

    @classmethod
    def register(cls, backend: str, store_class: type[BaseVectorStore]) -> None:
        """注册新的 VectorStore Backend

        接口签名：VectorStoreFactory.register(backend: str, store_class: type[BaseVectorStore]) -> None
        入参：
          - backend: 后端名称（如 "chroma"）
          - store_class: BaseVectorStore 子类

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增后端不改工厂代码
          - 对修改封闭：create() 方法不需要修改
        """
        if not issubclass(store_class, BaseVectorStore):
            raise VectorStoreError(f"注册失败: {store_class} 不是 BaseVectorStore 的子类")
        cls._BACKENDS[backend.lower().strip()] = store_class
