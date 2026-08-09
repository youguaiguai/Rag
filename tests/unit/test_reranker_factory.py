"""B5: Reranker 抽象接口与工厂测试

测试结构：
  1. RerankCandidate 数据契约测试（6 个）
  2. BaseReranker 抽象基类契约测试（8 个）
  3. NoneReranker 行为契约测试（10 个）
  4. RerankerFactory 工厂测试（8 个）
  5. 端到端集成测试（3 个）

合计 35 个测试

关键测试场景：
  - NoneReranker 不改变候选顺序
  - 工厂路由：enabled=false → NoneReranker
  - 工厂路由：backend="none" → NoneReranker
  - 工厂路由：未知 backend → RerankerError
  - 抽象基类不能实例化
  - 子类未实现 rerank → TypeError
"""

from __future__ import annotations

from typing import Any

import pytest
from core.settings import RerankSettings
from libs.reranker.base_reranker import (
    BaseReranker,
    RerankCandidate,
    RerankerError,
)
from libs.reranker.reranker_factory import (
    NoneReranker,
    RerankerFactory,
)


# ============================================================
# 测试工具函数
# ============================================================

def make_candidate(
    id: str = "c1",
    score: float = 0.9,
    text: str = "向量数据库是一种用于存储和检索向量的数据库系统。",
    metadata: dict[str, Any] | None = None,
) -> RerankCandidate:
    """创建测试用的 RerankCandidate

    知识点：测试工厂函数
      - 统一构造测试数据，减少重复代码
      - 默认值覆盖常见场景，特殊场景通过参数覆盖
    """
    if metadata is None:
        metadata = {"source": "doc.pdf", "page": 1}
    return RerankCandidate(id=id, score=score, text=text, metadata=metadata)


def make_candidates(n: int = 5) -> list[RerankCandidate]:
    """创建 n 个候选，score 从高到低排列

    知识点：测试数据设计
      - 模拟真实场景：粗排返回的候选按 score 降序排列
      - score 从 0.9 递减到 0.9 - (n-1)*0.1
    """
    return [
        make_candidate(
            id=f"c{i+1}",
            score=round(0.9 - i * 0.1, 4),
            text=f"候选文本 {i+1}",
            metadata={"source": f"doc_{i+1}.pdf", "page": i + 1},
        )
        for i in range(n)
    ]


# ============================================================
# 1. RerankCandidate 数据契约测试
# ============================================================

class TestRerankCandidate:
    """测试 RerankCandidate dataclass 的数据契约

    知识点：数据契约测试
      - 验证 dataclass 的字段定义、默认值、类型
      - 确保序列化/反序列化行为一致
    """

    def test_candidate_has_required_fields(self):
        """候选必须包含 id, score, text, metadata 四个字段"""
        c = RerankCandidate(id="c1", score=0.9, text="hello", metadata={"page": 1})
        assert c.id == "c1"
        assert c.score == 0.9
        assert c.text == "hello"
        assert c.metadata == {"page": 1}

    def test_candidate_metadata_defaults_to_empty_dict(self):
        """metadata 不传时默认为空字典"""
        c = RerankCandidate(id="c1", score=0.9, text="hello")
        assert c.metadata == {}

    def test_candidate_metadata_is_independent_per_instance(self):
        """每个实例的 metadata 默认值是独立的（不共享引用）"""
        c1 = RerankCandidate(id="c1", score=0.9, text="a")
        c2 = RerankCandidate(id="c2", score=0.8, text="b")
        c1.metadata["key"] = "value"
        assert "key" not in c2.metadata

    def test_candidate_is_mutable(self):
        """候选的字段可以被修改（重排后会更新 score）"""
        c = make_candidate(score=0.5)
        c.score = 0.99
        assert c.score == 0.99

    def test_candidate_equality(self):
        """两个相同字段值的候选相等"""
        c1 = RerankCandidate(id="c1", score=0.9, text="hello", metadata={"p": 1})
        c2 = RerankCandidate(id="c1", score=0.9, text="hello", metadata={"p": 1})
        assert c1 == c2

    def test_candidate_inequality(self):
        """任一字段不同则不相等"""
        c1 = RerankCandidate(id="c1", score=0.9, text="hello", metadata={})
        c2 = RerankCandidate(id="c2", score=0.9, text="hello", metadata={})
        assert c1 != c2


# ============================================================
# 2. BaseReranker 抽象基类契约测试
# ============================================================

class TestBaseRerankerContract:
    """测试 BaseReranker 抽象基类的契约约束

    知识点：ABC 契约测试
      - 验证抽象基类不能被实例化
      - 验证子类必须实现所有抽象方法
      - 验证实现类可以被实例化
    """

    def test_base_reranker_is_abstract(self):
        """BaseReranker 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError, match="abstract"):
            BaseReranker()

    def test_base_reranker_has_rerank_method(self):
        """BaseReranker 定义了 rerank 抽象方法"""
        assert hasattr(BaseReranker, "rerank")
        assert callable(getattr(BaseReranker, "rerank", None))

    def test_base_reranker_has_backend_name_property(self):
        """BaseReranker 定义了 backend_name 属性"""
        assert hasattr(BaseReranker, "backend_name")

    def test_subclass_missing_rerank_raises_typeerror(self):
        """子类不实现 rerank → TypeError"""

        class IncompleteReranker(BaseReranker):
            @property
            def backend_name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract"):
            IncompleteReranker()

    def test_subclass_missing_backend_name_raises_typeerror(self):
        """子类不实现 backend_name → TypeError"""

        class IncompleteReranker2(BaseReranker):
            def rerank(self, query, candidates, **kwargs):
                return candidates

        with pytest.raises(TypeError, match="abstract"):
            IncompleteReranker2()

    def test_complete_subclass_can_be_instantiated(self):
        """子类实现所有抽象方法后可以被实例化"""

        class CompleteReranker(BaseReranker):
            def rerank(self, query, candidates, **kwargs):
                return list(candidates)

            @property
            def backend_name(self) -> str:
                return "complete"

        r = CompleteReranker()
        assert isinstance(r, BaseReranker)
        assert r.backend_name == "complete"

    def test_rerank_accepts_query_and_candidates(self):
        """rerank 方法接受 query 和 candidates 参数"""

        class DummyReranker(BaseReranker):
            def rerank(self, query, candidates, **kwargs):
                assert isinstance(query, str)
                assert isinstance(candidates, list)
                return list(candidates)

            @property
            def backend_name(self) -> str:
                return "dummy"

        r = DummyReranker()
        result = r.rerank("query", [make_candidate()])
        assert len(result) == 1

    def test_rerank_returns_list_of_candidates(self):
        """rerank 方法返回 list[RerankCandidate]"""

        class DummyReranker2(BaseReranker):
            def rerank(self, query, candidates, **kwargs):
                return list(candidates)

            @property
            def backend_name(self) -> str:
                return "dummy"

        r = DummyReranker2()
        result = r.rerank("query", make_candidates(3))
        assert all(isinstance(c, RerankCandidate) for c in result)


# ============================================================
# 3. NoneReranker 行为契约测试
# ============================================================

class TestNoneRerankerContract:
    """测试 NoneReranker 的行为契约

    知识点：Null Object 模式
      - NoneReranker 是一个"什么都不做"的 Reranker
      - 它不改变候选顺序、不修改 score
      - 代替 None/null，让上层代码统一调用 rerank()

    验收标准：backend=none 时不会改变排序
    """

    def test_none_reranker_is_base_reranker(self):
        """NoneReranker 是 BaseReranker 的子类"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        assert isinstance(r, BaseReranker)

    def test_none_reranker_backend_name(self):
        """NoneReranker.backend_name 返回 'none'"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        assert r.backend_name == "none"

    def test_none_reranker_preserves_order(self):
        """NoneReranker.rerank 不改变候选顺序"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        candidates = make_candidates(5)
        result = r.rerank("查询", candidates)
        assert [c.id for c in result] == [c.id for c in candidates]

    def test_none_reranker_preserves_scores(self):
        """NoneReranker.rerank 不改变候选 score"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        candidates = make_candidates(3)
        result = r.rerank("查询", candidates)
        for orig, ranked in zip(candidates, result):
            assert orig.score == ranked.score

    def test_none_reranker_preserves_metadata(self):
        """NoneReranker.rerank 不改变候选 metadata"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        candidates = make_candidates(3)
        result = r.rerank("查询", candidates)
        for orig, ranked in zip(candidates, result):
            assert orig.metadata == ranked.metadata

    def test_none_reranker_preserves_text(self):
        """NoneReranker.rerank 不改变候选 text"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        candidates = make_candidates(3)
        result = r.rerank("查询", candidates)
        for orig, ranked in zip(candidates, result):
            assert orig.text == ranked.text

    def test_none_reranker_returns_same_length(self):
        """NoneReranker.rerank 返回的列表长度等于输入"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        for n in [0, 1, 5, 10]:
            candidates = make_candidates(n)
            result = r.rerank("查询", candidates)
            assert len(result) == n

    def test_none_reranker_empty_candidates(self):
        """NoneReranker.rerank 对空列表返回空列表"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        result = r.rerank("查询", [])
        assert result == []

    def test_none_reranker_single_candidate(self):
        """NoneReranker.rerank 对单个候选返回单个候选"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        c = make_candidate(id="only", score=0.5)
        result = r.rerank("查询", [c])
        assert len(result) == 1
        assert result[0].id == "only"

    def test_none_reranker_returns_copy_not_same_list(self):
        """NoneReranker.rerank 返回新列表，不返回原列表引用

        知识点：防御性拷贝
          - 返回 list(candidates) 而非 candidates
          - 避免外部修改影响内部状态
        """
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        candidates = make_candidates(3)
        result = r.rerank("查询", candidates)
        assert result is not candidates  # 不是同一个列表对象

    def test_none_reranker_accepts_extra_kwargs(self):
        """NoneReranker.rerank 接受 **kwargs（不报错）"""
        settings = RerankSettings(enabled=True, backend="none")
        r = NoneReranker(settings)
        result = r.rerank("查询", make_candidates(2), top_m=10, trace_id="abc")
        assert len(result) == 2


# ============================================================
# 4. RerankerFactory 工厂测试
# ============================================================

class TestRerankerFactory:
    """测试 RerankerFactory 的路由逻辑

    知识点：工厂模式测试
      - 验证不同配置创建不同的 Reranker 实例
      - 验证未支持 backend 抛出异常
      - 验证 register() 可动态注册新后端

    验收标准：backend=none 时不会改变排序；未知 backend 明确报错
    """

    def test_create_returns_none_reranker_for_backend_none(self):
        """backend="none" → 创建 NoneReranker"""
        settings = RerankSettings(enabled=True, backend="none")
        r = RerankerFactory.create(settings)
        assert isinstance(r, NoneReranker)
        assert r.backend_name == "none"

    def test_create_returns_none_reranker_when_disabled(self):
        """enabled=False → 创建 NoneReranker（降级，不报错）

        知识点：Reranker 的特殊性
          - Reranker 是可选组件，未启用时不应报错
          - 返回 NoneReranker 而非 None，让上层代码统一调用 rerank()
        """
        settings = RerankSettings(enabled=False, backend="cross_encoder")
        r = RerankerFactory.create(settings)
        assert isinstance(r, NoneReranker)

    def test_create_returns_none_reranker_when_disabled_even_with_unknown_backend(self):
        """enabled=False + 未知 backend → 仍然返回 NoneReranker

        知识点：enabled=False 优先于 backend 校验
          - 未启用时不关心 backend 是否有效
          - 直接返回 NoneReranker，不校验 backend
        """
        settings = RerankSettings(enabled=False, backend="unknown_backend")
        r = RerankerFactory.create(settings)
        assert isinstance(r, NoneReranker)

    def test_create_raises_error_for_unknown_backend(self):
        """enabled=True + 未知 backend → RerankerError"""
        settings = RerankSettings(enabled=True, backend="unknown_reranker")
        with pytest.raises(RerankerError, match="不支持"):
            RerankerFactory.create(settings)

    def test_create_error_message_lists_supported_backends(self):
        """异常消息中列出当前支持的后端"""
        settings = RerankSettings(enabled=True, backend="foobar")
        with pytest.raises(RerankerError) as exc_info:
            RerankerFactory.create(settings)
        assert "none" in str(exc_info.value)

    def test_create_is_case_insensitive(self):
        """backend 名称大小写不敏感"""
        settings = RerankSettings(enabled=True, backend="NONE")
        r = RerankerFactory.create(settings)
        assert isinstance(r, NoneReranker)

    def test_create_strips_whitespace(self):
        """backend 名称前后空白被去除"""
        settings = RerankSettings(enabled=True, backend="  none  ")
        r = RerankerFactory.create(settings)
        assert isinstance(r, NoneReranker)

    def test_register_adds_new_backend(self):
        """register() 可以注册新的 Reranker 后端

        知识点：开放-封闭原则
          - 新增后端不改 create() 代码
          - 通过 register() 动态注册
        """

        class CustomReranker(BaseReranker):
            def __init__(self, settings: RerankSettings) -> None:
                pass

            def rerank(self, query, candidates, **kwargs):
                return list(candidates)

            @property
            def backend_name(self) -> str:
                return "custom"

        RerankerFactory.register("custom", CustomReranker)
        try:
            settings = RerankSettings(enabled=True, backend="custom")
            r = RerankerFactory.create(settings)
            assert isinstance(r, CustomReranker)
            assert r.backend_name == "custom"
        finally:
            # 清理：移除注册的 backend，避免影响其他测试
            RerankerFactory._BACKENDS.pop("custom", None)

    def test_register_rejects_non_subclass(self):
        """register() 拒绝非 BaseReranker 子类"""

        class NotAReranker:
            pass

        with pytest.raises(RerankerError, match="不是 BaseReranker"):
            RerankerFactory.register("bad", NotAReranker)  # type: ignore


# ============================================================
# 5. 端到端集成测试
# ============================================================

class TestRerankerIntegration:
    """端到端集成测试：模拟完整的重排流程

    知识点：集成测试 vs 单元测试
      - 单元测试：测试单个组件的契约
      - 集成测试：测试多个组件协作的完整流程
    """

    def test_full_flow_none_reranker(self):
        """完整流程：创建 NoneReranker → rerank → 验证结果不变

        模拟场景：
          1. 配置 rerank.backend="none"
          2. 工厂创建 NoneReranker
          3. 粗排返回 5 个候选
          4. NoneReranker.rerank 不改变顺序
          5. Top-K 结果与输入一致
        """
        settings = RerankSettings(enabled=True, backend="none")
        reranker = RerankerFactory.create(settings)

        candidates = make_candidates(5)
        query = "什么是向量数据库？"
        ranked = reranker.rerank(query, candidates)

        assert len(ranked) == 5
        assert [c.id for c in ranked] == [c.id for c in candidates]
        assert ranked[0].score >= ranked[-1].score  # 原顺序保持

    def test_full_flow_disabled_reranker(self):
        """完整流程：enabled=False → NoneReranker → 结果不变"""
        settings = RerankSettings(enabled=False, backend="cross_encoder")
        reranker = RerankerFactory.create(settings)

        assert isinstance(reranker, NoneReranker)
        candidates = make_candidates(3)
        ranked = reranker.rerank("query", candidates)
        assert [c.id for c in ranked] == [c.id for c in candidates]

    def test_full_flow_with_custom_reranker_registered(self):
        """完整流程：注册自定义 Reranker → 工厂创建 → rerank → 验证

        模拟 B7.7/B7.8 阶段实现 CrossEncoder/LLM Reranker 后的场景
        """

        class MockCrossEncoderReranker(BaseReranker):
            """模拟 CrossEncoder Reranker — 反转顺序

            知识点：测试替身 (Test Double)
              - 用一个简单的"反转顺序"实现模拟 CrossEncoder
              - 不需要真正调用模型，只需验证工厂路由正确
            """

            def __init__(self, settings: RerankSettings) -> None:
                pass

            def rerank(self, query, candidates, **kwargs):
                return list(reversed(candidates))

            @property
            def backend_name(self) -> str:
                return "mock_cross_encoder"

        RerankerFactory.register("mock_ce", MockCrossEncoderReranker)
        try:
            settings = RerankSettings(enabled=True, backend="mock_ce")
            reranker = RerankerFactory.create(settings)
            assert isinstance(reranker, MockCrossEncoderReranker)

            candidates = make_candidates(3)
            ranked = reranker.rerank("query", candidates)
            assert [c.id for c in ranked] == ["c3", "c2", "c1"]  # 反转
        finally:
            RerankerFactory._BACKENDS.pop("mock_ce", None)

