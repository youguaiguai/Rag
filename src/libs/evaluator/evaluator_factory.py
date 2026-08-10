"""
Evaluator 工厂 — 根据配置创建对应的 Evaluator 实例

知识点：
  - 工厂模式 (Factory Pattern)：将"创建哪个实现"的决策从业务代码中解耦
  - 核心方法：EvaluatorFactory.create(backend: str, **kwargs) -> BaseEvaluator
  - 配置驱动：settings.evaluation.backends 决定创建哪些 Evaluator
  - 好处：切换评估后端只改配置，不改代码

工厂路由逻辑：
  backend="custom"  → CustomEvaluator（轻量检索指标：hit_rate, mrr, recall, precision）
  backend="ragas"   → RagasEvaluator（H1 阶段实现，LLM-as-Judge 生成指标）

当前阶段（B6）：
  - 只实现 CustomEvaluator，验证工厂路由逻辑
  - RagasEvaluator 在 H1 阶段实现
  - 面试考点："为什么先实现 Custom？" → 轻量快速，不依赖 LLM，适合 CI/CD

接口签名：
  EvaluatorFactory.create(backend: str, **kwargs) -> BaseEvaluator
    入参：
      - backend: 评估后端名称（如 "custom"）
      - **kwargs: 传递给 Evaluator 构造函数的参数（如 top_k=10）
    出参：BaseEvaluator 子类实例
    异常：EvaluatorError — backend 不支持
"""

from __future__ import annotations

from libs.evaluator.base_evaluator import BaseEvaluator, EvaluatorError
from libs.evaluator.custom_evaluator import CustomEvaluator


# ============================================================
# Evaluator 工厂
# ============================================================

class EvaluatorFactory:
    """Evaluator 工厂 — 根据 backend 名称创建对应的 Evaluator 实例

    接口签名：
      EvaluatorFactory.create(backend: str, **kwargs) -> BaseEvaluator

    知识点：工厂模式 + 可扩展性
      - 从 backend 参数获取后端名称
      - 在 _BACKENDS 映射表中查找对应的实现类
      - 创建实例并传入 kwargs
      - 未找到则抛出 EvaluatorError

    与 B1-B5 工厂的区别：
      - B1-B4 工厂：create(settings) 传入 Settings 对象
      - B5 工厂：create(settings) 且 enabled=False 时返回 NoneReranker
      - B6 工厂：create(backend, **kwargs) 更灵活，直接传后端名称和参数
      - 原因：EvaluationSettings.backends 是 List[str]（多个后端），
        需要逐个创建，所以工厂接受 backend 字符串而非 Settings 对象
      - 面试考点："为什么 B6 工厂不接受 Settings？" → backends 是列表，需逐个创建

    组合模式支持：
      - 上层代码遍历 settings.evaluation.backends
      - 对每个 backend 调用 EvaluatorFactory.create(backend)
      - 将多个 Evaluator 组合为 CompositeEvaluator（H2 阶段实现）
    """

    # Backend → 实现类的映射表
    _BACKENDS: dict[str, type[BaseEvaluator]] = {
        "custom": CustomEvaluator,
    }

    @classmethod
    def create(cls, backend: str, **kwargs) -> BaseEvaluator:
        """根据 backend 名称创建 Evaluator 实例

        接口签名：EvaluatorFactory.create(backend: str, **kwargs) -> BaseEvaluator
        入参：
          - backend: 后端名称（如 "custom"）
          - **kwargs: 传递给 Evaluator 构造函数的参数（如 top_k=10）
        出参：BaseEvaluator 子类实例
        异常：EvaluatorError — backend 不支持

        处理流程：
          1. 从 backend 参数获取后端名称
          2. 在 _BACKENDS 映射表中查找对应的实现类
          3. 创建实例并传入 kwargs
          4. 未找到则抛出 EvaluatorError

        面试考点：
          "新增评估后端需要改什么？" → 实现 BaseEvaluator + 在 _BACKENDS 注册 或 调用 register()
          "create 方法的 kwargs 有什么用？" → 传递后端特定参数（如 CustomEvaluator 的 top_k）
        """
        backend_lower = backend.lower().strip()

        if backend_lower not in cls._BACKENDS:
            supported = ", ".join(sorted(cls._BACKENDS.keys()))
            raise EvaluatorError(
                f"不支持的 Evaluator backend: '{backend}'。"
                f"当前支持: [{supported}]"
            )

        evaluator_class = cls._BACKENDS[backend_lower]
        return evaluator_class(**kwargs)

    @classmethod
    def register(cls, backend: str, evaluator_class: type[BaseEvaluator]) -> None:
        """注册新的 Evaluator Backend

        接口签名：EvaluatorFactory.register(backend: str, evaluator_class: type[BaseEvaluator]) -> None
        入参：
          - backend: 后端名称（如 "ragas"）
          - evaluator_class: BaseEvaluator 子类

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增后端不改工厂代码
          - 对修改封闭：create() 方法不需要修改
        """
        if not issubclass(evaluator_class, BaseEvaluator):
            raise EvaluatorError(f"注册失败: {evaluator_class} 不是 BaseEvaluator 的子类")
        cls._BACKENDS[backend.lower().strip()] = evaluator_class

    @classmethod
    def supported_backends(cls) -> list[str]:
        """返回当前支持的所有后端名称

        接口签名：EvaluatorFactory.supported_backends() -> list[str]
        出参：支持的后端名称列表

        知识点：内省方法
          - 让上层代码可以查询当前支持哪些后端
          - 用于配置校验和 UI 展示
        """
        return sorted(cls._BACKENDS.keys())
