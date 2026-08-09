"""
Embedding 工厂 — 根据配置创建对应的 Embedding 实例

知识点：
  - 工厂模式 (Factory Pattern)：将"创建哪个实现"的决策从业务代码中解耦
  - 核心方法：EmbeddingFactory.create(settings) -> BaseEmbedding
  - 配置驱动：settings.embedding.provider 决定创建哪个 Embedding 实例
  - 好处：切换 Provider 只改配置，不改代码

工厂路由逻辑：
  provider="openai"   → OpenAIEmbedding（需安装 openai 包）
  provider="azure"    → AzureEmbedding（需安装 openai 包 + azure 配置）
  provider="ollama"   → OllamaEmbedding（需 ollama 服务运行）
  provider="fake"     → FakeEmbedding（测试桩，不调用真实 API）

当前阶段（B2）：
  - 只实现 FakeEmbedding（测试桩），验证工厂路由逻辑
  - OpenAI/Azure/Ollama 实现在后续阶段（B7.3-B7.4）添加
  - 面试考点："为什么先用 Fake 实现？" → 隔离测试 + 不依赖外部服务

接口签名：
  EmbeddingFactory.create(settings: EmbeddingSettings) -> BaseEmbedding
    入参：Embedding 配置对象
    出参：BaseEmbedding 子类实例
    异常：EmbeddingError — provider 不支持 / 依赖缺失
"""

from __future__ import annotations

import hashlib
from typing import Any

from core.settings import EmbeddingSettings
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError


# ============================================================
# FakeEmbedding — 测试桩
# ============================================================

class FakeEmbedding(BaseEmbedding):
    """Fake Embedding 实现 — 测试专用，不调用真实 API

    知识点：测试桩 (Test Stub / Test Double)
      - 目的：隔离测试，不依赖真实 API（省流量 + 省钱 + 稳定）
      - 行为：基于文本哈希生成确定性向量，相同文本始终产生相同向量
      - 面试考点："什么是测试桩？" → 替代真实依赖的可控实现

    确定性向量生成策略：
      - 对输入文本取 SHA256 哈希
      - 将哈希的字节序列映射为浮点数列表
      - 截断或填充到指定维度
      - 好处：相同文本 → 相同向量（可重复测试），不同文本 → 不同向量（基本区分能力）

    使用场景：
      - 工厂路由测试：验证 EmbeddingFactory.create() 能正确创建 FakeEmbedding
      - 集成测试：在完整 Pipeline 中使用 FakeEmbedding 替代真实 API
      - 回归测试：FakeEmbedding 返回稳定向量，确保测试可重复
    """

    def __init__(self, settings: EmbeddingSettings) -> None:
        """初始化 FakeEmbedding

        接口签名：FakeEmbedding(settings: EmbeddingSettings)
        入参：
          - settings: Embedding 配置（包含 model、dimensions 等）
        """
        self._model_name = settings.model or "fake-embedding-model"
        self._dimensions = settings.dimensions if settings.dimensions > 0 else 128

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """将文本列表转换为向量（基于哈希的确定性生成）

        知识点：FakeEmbedding.embed() 的行为设计
          - 不调用任何外部 API，纯本地计算
          - 相同文本 → 相同向量（SHA256 确定性）
          - 不同文本 → 不同向量（哈希碰撞概率极低）
          - 向量值归一化到 [-1, 1] 区间，模拟真实 Embedding 的值域

        面试考点："FakeEmbedding 和真实 Embedding 的区别？"
          → Fake 用哈希模拟，无语义理解能力；真实模型能捕获语义相似性
        """
        if not texts:
            return []

        vectors: list[list[float]] = []
        for text in texts:
            # SHA256 哈希 → 确定性字节序列
            hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()

            # 将字节映射为浮点数，归一化到 [-1, 1]
            # 每个 byte (0-255) → (byte - 128) / 128 → [-1, 1)
            raw_floats = [(b - 128) / 128.0 for b in hash_bytes]

            # 扩展或截断到目标维度
            if len(raw_floats) >= self._dimensions:
                vector = raw_floats[:self._dimensions]
            else:
                # 哈希字节不够时循环填充（32 字节 → 维度可能 > 32）
                vector = []
                while len(vector) < self._dimensions:
                    vector.extend(raw_floats)
                vector = vector[:self._dimensions]

            vectors.append(vector)

        return vectors

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model_name

    @property
    def dimensions(self) -> int:
        """返回向量维度"""
        return self._dimensions


# ============================================================
# Embedding 工厂
# ============================================================

class EmbeddingFactory:
    """Embedding 工厂 — 根据 settings.embedding.provider 创建对应的 Embedding 实例

    接口签名：
      EmbeddingFactory.create(settings: EmbeddingSettings) -> BaseEmbedding

    知识点：工厂模式的三种实现方式
      1. 简单工厂（本项目采用）：一个 create 方法 + 映射表
      2. 工厂方法：每个产品一个工厂类（过度设计）
      3. 抽象工厂：一组相关产品的工厂（本项目不需要）

    为什么选简单工厂？
      - Embedding Provider 数量有限（3-4 个），映射表够用
      - 代码直观，新人一眼看懂
      - 面试考点："简单工厂 vs 工厂方法？" → 产品少用简单工厂，多用工厂方法
    """

    # Provider → 实现类的映射表
    # 知识点：用映射表代替 if/elif，更易扩展
    #   新增 Provider 只需加一行映射，不用改 create() 方法
    _PROVIDERS: dict[str, type[BaseEmbedding]] = {
        "fake": FakeEmbedding,
    }

    @classmethod
    def create(cls, settings: EmbeddingSettings) -> BaseEmbedding:
        """根据配置创建 Embedding 实例

        接口签名：EmbeddingFactory.create(settings: EmbeddingSettings) -> BaseEmbedding
        入参：Embedding 配置对象（包含 provider、model、dimensions、api_key 等）
        出参：BaseEmbedding 子类实例
        异常：EmbeddingError — provider 不支持

        处理流程：
          1. 从 settings.provider 获取 provider 名称
          2. 在 _PROVIDERS 映射表中查找对应的实现类
          3. 创建实例并传入 settings
          4. 未找到则抛出 EmbeddingError

        面试考点：
          "工厂模式的好处？" → 改配置不改代码 + 上层只依赖接口
          "新增 Provider 需要改什么？" → 实现 BaseEmbedding + 在 _PROVIDERS 注册
        """
        provider = settings.provider.lower().strip()

        if provider not in cls._PROVIDERS:
            supported = ", ".join(sorted(cls._PROVIDERS.keys()))
            raise EmbeddingError(
                f"不支持的 Embedding provider: '{provider}'。"
                f"当前支持: [{supported}]"
            )

        embedding_class = cls._PROVIDERS[provider]
        return embedding_class(settings)

    @classmethod
    def register(cls, provider: str, embedding_class: type[BaseEmbedding]) -> None:
        """注册新的 Embedding Provider

        接口签名：EmbeddingFactory.register(provider: str, embedding_class: type[BaseEmbedding]) -> None
        入参：
          - provider: Provider 名称（如 "openai"）
          - embedding_class: BaseEmbedding 子类

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增 Provider 不改工厂代码
          - 对修改封闭：create() 方法不需要修改
          - register() 让第三方代码可以注册自己的 Provider
        """
        if not issubclass(embedding_class, BaseEmbedding):
            raise EmbeddingError(f"注册失败: {embedding_class} 不是 BaseEmbedding 的子类")
        cls._PROVIDERS[provider.lower().strip()] = embedding_class
