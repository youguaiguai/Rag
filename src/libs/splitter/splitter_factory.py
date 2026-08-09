"""
Splitter 工厂 — 根据配置创建对应的 Splitter 实例

知识点：
  - 工厂模式 (Factory Pattern)：将"创建哪个实现"的决策从业务代码中解耦
  - 核心方法：SplitterFactory.create(settings) -> BaseSplitter
  - 配置驱动：settings.splitter.provider 决定创建哪个 Splitter 实例
  - 好处：切换切分策略只改配置，不改代码

工厂路由逻辑：
  provider="recursive" → RecursiveSplitter（B7.5 实现，封装 LangChain）
  provider="semantic"  → SemanticSplitter（未来实现，基于 Embedding 相似度）
  provider="fixed"     → FixedLengthSplitter（未来实现，定长切分）
  provider="fake"      → FakeSplitter（测试桩，不依赖外部库）

当前阶段（B3）：
  - 只实现 FakeSplitter（测试桩），验证工厂路由逻辑
  - RecursiveSplitter 在 B7.5 阶段实现（需要 LangChain text-splitters）
  - 面试考点："为什么先用 Fake 实现？" → 隔离测试 + 不依赖外部库

接口签名：
  SplitterFactory.create(settings: SplitterSettings) -> BaseSplitter
    入参：Splitter 配置对象
    出参：BaseSplitter 子类实例
    异常：SplitterError — provider 不支持 / 依赖缺失
"""

from __future__ import annotations

from typing import Any

from core.settings import SplitterSettings
from libs.splitter.base_splitter import BaseSplitter, SplitterError


# ============================================================
# FakeSplitter — 测试桩
# ============================================================

class FakeSplitter(BaseSplitter):
    """Fake Splitter 实现 — 测试专用，不依赖外部库

    知识点：测试桩 (Test Stub / Test Double)
      - 目的：隔离测试，不依赖 LangChain 等外部库
      - 行为：按 chunk_size 简单定长切分，保留 chunk_overlap 重叠
      - 面试考点："什么是测试桩？" → 替代真实依赖的可控实现

    切分策略（简化版定长切分）：
      - 按 chunk_size 字符数切分
      - 相邻 chunk 之间有 chunk_overlap 字符的重叠
      - 重叠保证上下文连续性（一个语义单元被切断时，下一个 chunk 能接上）
      - 空字符串返回空列表

    使用场景：
      - 工厂路由测试：验证 SplitterFactory.create() 能正确创建 FakeSplitter
      - 集成测试：在完整 Pipeline 中使用 FakeSplitter 替代真实切分器
      - 回归测试：FakeSplitter 行为简单确定，确保测试可重复
    """

    def __init__(self, settings: SplitterSettings) -> None:
        """初始化 FakeSplitter

        接口签名：FakeSplitter(settings: SplitterSettings)
        入参：
          - settings: Splitter 配置（包含 chunk_size、chunk_overlap 等）
        """
        self._provider_name = "fake"
        self._chunk_size = settings.chunk_size if settings.chunk_size > 0 else 1000
        self._chunk_overlap = settings.chunk_overlap if settings.chunk_overlap >= 0 else 200

    def split_text(self, text: str, **kwargs: Any) -> list[str]:
        """按定长切分文本，保留重叠

        知识点：FakeSplitter.split_text() 的行为设计
          - 简化的定长切分：按 chunk_size 切分，相邻 chunk 有 chunk_overlap 重叠
          - 不做语义感知，纯粹按字符位置切分
          - 空字符串返回空列表
          - 短文本（<= chunk_size）返回单元素列表

        面试考点："FakeSplitter 和 RecursiveSplitter 的区别？"
          → Fake 按字符位置机械切分；Recursive 按分隔符层级递归切分，保持语义边界

        切分示例：
          text = "abcdefghij" (10 字符)
          chunk_size = 4, chunk_overlap = 2
          → ["abcd", "cdef", "efgh", "ghij"]
          step = chunk_size - chunk_overlap = 2
        """
        if not text:
            return []

        # step = 每次前进的字符数 = chunk_size - chunk_overlap
        # 当 overlap >= chunk_size 时，step <= 0，会导致死循环
        # 此时退化为无重叠切分（step = chunk_size）
        step = self._chunk_size - self._chunk_overlap
        if step <= 0:
            step = self._chunk_size

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += step

        return chunks

    @property
    def provider_name(self) -> str:
        """返回切分策略名称"""
        return self._provider_name


# ============================================================
# Splitter 工厂
# ============================================================

class SplitterFactory:
    """Splitter 工厂 — 根据 settings.splitter.provider 创建对应的 Splitter 实例

    接口签名：
      SplitterFactory.create(settings: SplitterSettings) -> BaseSplitter

    知识点：工厂模式的三种实现方式
      1. 简单工厂（本项目采用）：一个 create 方法 + 映射表
      2. 工厂方法：每个产品一个工厂类（过度设计）
      3. 抽象工厂：一组相关产品的工厂（本项目不需要）

    为什么选简单工厂？
      - Splitter 策略数量有限（3-4 种），映射表够用
      - 代码直观，新人一眼看懂
      - 与 LLMFactory / EmbeddingFactory 保持一致的设计模式
    """

    # Provider → 实现类的映射表
    # 知识点：用映射表代替 if/elif，更易扩展
    #   新增策略只需加一行映射，不用改 create() 方法
    _PROVIDERS: dict[str, type[BaseSplitter]] = {
        "fake": FakeSplitter,
    }

    @classmethod
    def create(cls, settings: SplitterSettings) -> BaseSplitter:
        """根据配置创建 Splitter 实例

        接口签名：SplitterFactory.create(settings: SplitterSettings) -> BaseSplitter
        入参：Splitter 配置对象（包含 provider、chunk_size、chunk_overlap 等）
        出参：BaseSplitter 子类实例
        异常：SplitterError — provider 不支持

        处理流程：
          1. 从 settings.provider 获取 provider 名称
          2. 在 _PROVIDERS 映射表中查找对应的实现类
          3. 创建实例并传入 settings
          4. 未找到则抛出 SplitterError

        面试考点：
          "工厂模式的好处？" → 改配置不改代码 + 上层只依赖接口
          "新增切分策略需要改什么？" → 实现 BaseSplitter + 在 _PROVIDERS 注册
        """
        provider = settings.provider.lower().strip()

        if provider not in cls._PROVIDERS:
            supported = ", ".join(sorted(cls._PROVIDERS.keys()))
            raise SplitterError(
                f"不支持的 Splitter provider: '{provider}'。"
                f"当前支持: [{supported}]"
            )

        splitter_class = cls._PROVIDERS[provider]
        return splitter_class(settings)

    @classmethod
    def register(cls, provider: str, splitter_class: type[BaseSplitter]) -> None:
        """注册新的 Splitter Provider

        接口签名：SplitterFactory.register(provider: str, splitter_class: type[BaseSplitter]) -> None
        入参：
          - provider: Provider 名称（如 "recursive"）
          - splitter_class: BaseSplitter 子类

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增策略不改工厂代码
          - 对修改封闭：create() 方法不需要修改
          - register() 让第三方代码可以注册自己的策略
        """
        if not issubclass(splitter_class, BaseSplitter):
            raise SplitterError(f"注册失败: {splitter_class} 不是 BaseSplitter 的子类")
        cls._PROVIDERS[provider.lower().strip()] = splitter_class
