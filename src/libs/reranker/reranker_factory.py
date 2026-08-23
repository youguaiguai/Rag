"""
Reranker 工厂 — 根据配置创建对应的 Reranker 实例

知识点：
  - 工厂模式 (Factory Pattern)：将"创建哪个实现"的决策从业务代码中解耦
  - 核心方法：RerankerFactory.create(settings) -> BaseReranker
  - 配置驱动：settings.rerank.backend 决定创建哪个 Reranker 实例
  - 好处：切换重排后端只改配置，不改代码

工厂路由逻辑：
  backend="none"           → NoneReranker（默认回退，不重排）
  backend="cross_encoder"  → CrossEncoderReranker（B7.8 实现，CrossEncoder 精排）
  backend="llm"            → LLMReranker（B7.7 实现，LLM 打分）

当前阶段（B5）：
  - 只实现 NoneReranker（默认回退），验证工厂路由逻辑
  - CrossEncoderReranker / LLMReranker 在 B7.7/B7.8 阶段实现
  - 面试考点："为什么先实现 None？" → 保证系统始终可用，Reranker 失败时有回退

接口签名：
  RerankerFactory.create(settings: RerankSettings) -> BaseReranker
    入参：Rerank 配置对象
    出参：BaseReranker 子类实例
    异常：RerankerError — backend 不支持 / 依赖缺失
"""

from __future__ import annotations

from core.settings import RerankSettings
from libs.llm.base_llm import BaseLLM
from libs.reranker.base_reranker import BaseReranker, RerankCandidate, RerankerError
from libs.reranker.cross_encoder_reranker import CrossEncoderReranker
from libs.reranker.llm_reranker import LLMReranker
from typing import Any


# ============================================================
# NoneReranker — 默认回退（不重排）
# ============================================================

class NoneReranker(BaseReranker):
    """None Reranker 实现 — 不做任何重排，保持原顺序

    知识点：默认回退（Fallback）策略
      - 目的：当 Reranker 未启用或失败时，系统仍能正常返回结果
      - 行为：直接返回原候选列表，不改变顺序和 score
      - 面试考点："为什么需要 NoneReranker？" → 保证系统可用性，降级而非报错

    使用场景：
      1. 配置 rerank.enabled=false → 工厂返回 NoneReranker
      2. 配置 rerank.backend="none" → 工厂返回 NoneReranker
      3. D6 阶段：CrossEncoder/LLM Reranker 失败时，Core 层 fallback 到 NoneReranker

    设计模式：Null Object 模式（空对象模式）
      - 用一个"什么都不做"的对象代替 None/null
      - 好处：上层代码不需要判空，统一调用 rerank() 接口
      - 面试考点："Null Object 模式？" → 用空行为对象代替 null 检查
    """

    def __init__(self, settings: RerankSettings) -> None:
        """初始化 NoneReranker

        接口签名：NoneReranker(settings: RerankSettings)
        入参：
          - settings: Rerank 配置（NoneReranker 实际不使用配置，但保持接口一致）
        """
        pass  # NoneReranker 不需要任何配置

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        **kwargs: Any,
    ) -> list[RerankCandidate]:
        """直接返回原候选列表，不改变顺序

        知识点：NoneReranker.rerank() 的行为设计
          - 不做任何计算，直接返回原列表
          - 顺序不变、score 不变
          - 即使 candidates 为空列表，也正常返回空列表

        面试考点："NoneReranker 和不调用 rerank 有什么区别？"
          → 行为相同，但 NoneReranker 让上层代码统一调用 rerank() 接口，不需要判空
          → 这是 Null Object 模式的核心价值
        """
        # 直接返回原列表的副本，避免外部修改影响内部状态
        return list(candidates)

    @property
    def backend_name(self) -> str:
        """返回后端名称"""
        return "none"


# ============================================================
# Reranker 工厂
# ============================================================

class RerankerFactory:
    """Reranker 工厂 — 根据 settings.rerank.backend 创建对应的 Reranker 实例

    接口签名：
      RerankerFactory.create(settings: RerankSettings) -> BaseReranker

    知识点：工厂模式 + 默认回退
      - 当 enabled=false 时，返回 NoneReranker（默认回退）
      - 当 backend="none" 时，返回 NoneReranker
      - 当 backend 不支持时，抛出 RerankerError
      - 面试考点："RerankerFactory 如何处理未启用的情况？" → 返回 NoneReranker 而非 None

    与 B1-B4 工厂的区别：
      - 其他工厂：不支持的 provider 直接报错
      - RerankerFactory：enabled=false 时不报错，返回 NoneReranker（降级）
      - 这是 Reranker 的特殊性：它是可选组件，不启用时系统仍需正常工作
    """

    # Backend → 实现类的映射表
    _BACKENDS: dict[str, type[BaseReranker]] = {
        "none": NoneReranker,
        "llm": LLMReranker,
        "cross_encoder": CrossEncoderReranker,
    }

    @classmethod
    def create(cls, settings: RerankSettings, llm: BaseLLM | None = None, **kwargs: Any) -> BaseReranker:
        """根据配置创建 Reranker 实例

        接口签名：RerankerFactory.create(settings: RerankSettings) -> BaseReranker
        入参：Rerank 配置对象（包含 enabled、backend、model、top_m 等）
        出参：BaseReranker 子类实例
        异常：RerankerError — backend 不支持

        处理流程：
          1. 如果 enabled=false → 返回 NoneReranker（默认回退）
          2. 从 settings.backend 获取 backend 名称
          3. 在 _BACKENDS 映射表中查找对应的实现类
          4. 创建实例并传入 settings
          5. 未找到则抛出 RerankerError

        面试考点：
          "Reranker 未启用时工厂返回什么？" → NoneReranker（不是 None）
          "新增重排后端需要改什么？" → 实现 BaseReranker + 在 _BACKENDS 注册
        """
        # 未启用时返回 NoneReranker（降级，不报错）
        if not settings.enabled:
            return NoneReranker(settings)

        backend = settings.backend.lower().strip()

        if backend not in cls._BACKENDS:
            supported = ", ".join(sorted(cls._BACKENDS.keys()))
            raise RerankerError(
                f"不支持的 Reranker backend: '{backend}'。"
                f"当前支持: [{supported}]"
            )

        reranker_class = cls._BACKENDS[backend]
        # LLM Reranker 需要 llm 参数
        if backend == "llm":
            if llm is None:
                raise RerankerError("LLM Reranker 需要传入 llm 参数")
            return reranker_class(settings, llm=llm, **kwargs)
        return reranker_class(settings)

    @classmethod
    def register(cls, backend: str, reranker_class: type[BaseReranker]) -> None:
        """注册新的 Reranker Backend

        接口签名：RerankerFactory.register(backend: str, reranker_class: type[BaseReranker]) -> None
        入参：
          - backend: 后端名称（如 "cross_encoder"）
          - reranker_class: BaseReranker 子类

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增后端不改工厂代码
          - 对修改封闭：create() 方法不需要修改
        """
        if not issubclass(reranker_class, BaseReranker):
            raise RerankerError(f"注册失败: {reranker_class} 不是 BaseReranker 的子类")
        cls._BACKENDS[backend.lower().strip()] = reranker_class
