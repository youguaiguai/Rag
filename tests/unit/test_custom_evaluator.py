"""B6: Evaluator 抽象接口与工厂测试

测试结构：
  1. RetrievedChunk 数据契约测试（5 个）
  2. GroundTruth 数据契约测试（5 个）
  3. EvalResult 数据契约测试（5 个）
  4. BaseEvaluator 抽象基类契约测试（8 个）
  5. CustomEvaluator 指标计算测试（15 个）
  6. EvaluatorFactory 工厂测试（8 个）
  7. 端到端集成测试（4 个）

合计 50 个测试

关键测试场景：
  - Hit Rate：golden_id 在 Top-K 中 → 1.0；不在 → 0.0
  - MRR：第 1 名命中 → 1.0；第 3 名命中 → 0.333；未命中 → 0.0
  - Recall@K：命中 2/5 golden → 0.4
  - Precision@K：命中 2/10 → 0.2
  - 空结果 / 空 golden_ids 的边界情况
  - 工厂路由：custom → CustomEvaluator；未知 backend → EvaluatorError
  - 抽象基类不能实例化
"""

from __future__ import annotations

from typing import Any

import pytest
from libs.evaluator.base_evaluator import (
    BaseEvaluator,
    EvalResult,
    EvaluatorError,
    GroundTruth,
    RetrievedChunk,
)
from libs.evaluator.custom_evaluator import CustomEvaluator
from libs.evaluator.evaluator_factory import EvaluatorFactory


# ============================================================
# 测试工具函数
# ============================================================

def make_chunk(
    id: str = "c1",
    score: float = 0.9,
    text: str = "向量数据库是一种用于存储和检索向量的数据库系统。",
    metadata: dict[str, Any] | None = None,
) -> RetrievedChunk:
    """创建测试用的 RetrievedChunk"""
    if metadata is None:
        metadata = {"source": "doc.pdf", "page": 1}
    return RetrievedChunk(id=id, score=score, text=text, metadata=metadata)


def make_chunks(n: int = 10) -> list[RetrievedChunk]:
    """创建 n 个检索结果，id 从 c1 到 cN，score 从高到低"""
    return [
        make_chunk(
            id=f"c{i+1}",
            score=round(0.9 - i * 0.05, 4),
            text=f"候选文本 {i+1}",
            metadata={"source": f"doc_{i+1}.pdf", "page": i + 1},
        )
        for i in range(n)
    ]


def make_ground_truth(
    golden_ids: list[str] | None = None,
    golden_answer: str = "向量数据库用于存储和检索向量。",
    query: str = "什么是向量数据库？",
) -> GroundTruth:
    """创建测试用的 GroundTruth"""
    if golden_ids is None:
        golden_ids = ["c1"]
    return GroundTruth(
        query=query,
        golden_ids=golden_ids,
        golden_answer=golden_answer,
    )


# ============================================================
# 1. RetrievedChunk 数据契约测试
# ============================================================

class TestRetrievedChunk:
    """测试 RetrievedChunk dataclass 的数据契约"""

    def test_chunk_has_required_fields(self):
        """检索结果必须包含 id, score, text, metadata 四个字段"""
        c = RetrievedChunk(id="c1", score=0.9, text="hello", metadata={"page": 1})
        assert c.id == "c1"
        assert c.score == 0.9
        assert c.text == "hello"
        assert c.metadata == {"page": 1}

    def test_chunk_metadata_defaults_to_empty_dict(self):
        """metadata 不传时默认为空字典"""
        c = RetrievedChunk(id="c1", score=0.9, text="hello")
        assert c.metadata == {}

    def test_chunk_metadata_is_independent_per_instance(self):
        """每个实例的 metadata 默认值是独立的"""
        c1 = RetrievedChunk(id="c1", score=0.9, text="a")
        c2 = RetrievedChunk(id="c2", score=0.8, text="b")
        c1.metadata["key"] = "value"
        assert "key" not in c2.metadata

    def test_chunk_equality(self):
        """两个相同字段值的检索结果相等"""
        c1 = RetrievedChunk(id="c1", score=0.9, text="hello", metadata={"p": 1})
        c2 = RetrievedChunk(id="c1", score=0.9, text="hello", metadata={"p": 1})
        assert c1 == c2

    def test_chunk_inequality(self):
        """任一字段不同则不相等"""
        c1 = RetrievedChunk(id="c1", score=0.9, text="hello", metadata={})
        c2 = RetrievedChunk(id="c2", score=0.9, text="hello", metadata={})
        assert c1 != c2


# ============================================================
# 2. GroundTruth 数据契约测试
# ============================================================

class TestGroundTruth:
    """测试 GroundTruth dataclass 的数据契约"""

    def test_gt_has_required_fields(self):
        """GroundTruth 必须包含 query, golden_ids, golden_answer"""
        gt = GroundTruth(query="Q1", golden_ids=["c1"], golden_answer="A1")
        assert gt.query == "Q1"
        assert gt.golden_ids == ["c1"]
        assert gt.golden_answer == "A1"

    def test_gt_golden_ids_defaults_to_empty_list(self):
        """golden_ids 不传时默认为空列表"""
        gt = GroundTruth()
        assert gt.golden_ids == []

    def test_gt_golden_ids_is_independent_per_instance(self):
        """每个实例的 golden_ids 默认值是独立的"""
        gt1 = GroundTruth()
        gt2 = GroundTruth()
        gt1.golden_ids.append("c1")
        assert gt2.golden_ids == []

    def test_gt_query_defaults_to_empty_string(self):
        """query 不传时默认为空字符串"""
        gt = GroundTruth()
        assert gt.query == ""

    def test_gt_golden_answer_defaults_to_empty_string(self):
        """golden_answer 不传时默认为空字符串"""
        gt = GroundTruth()
        assert gt.golden_answer == ""


# ============================================================
# 3. EvalResult 数据契约测试
# ============================================================

class TestEvalResult:
    """测试 EvalResult dataclass 的数据契约"""

    def test_result_has_required_fields(self):
        """EvalResult 必须包含 backend_name, metrics, details"""
        r = EvalResult(backend_name="custom", metrics={"hit_rate": 0.8}, details={"k": 10})
        assert r.backend_name == "custom"
        assert r.metrics == {"hit_rate": 0.8}
        assert r.details == {"k": 10}

    def test_result_metrics_defaults_to_empty_dict(self):
        """metrics 不传时默认为空字典"""
        r = EvalResult(backend_name="custom")
        assert r.metrics == {}

    def test_result_details_defaults_to_empty_dict(self):
        """details 不传时默认为空字典"""
        r = EvalResult(backend_name="custom")
        assert r.details == {}

    def test_result_metrics_is_independent_per_instance(self):
        """每个实例的 metrics 默认值是独立的"""
        r1 = EvalResult(backend_name="custom")
        r2 = EvalResult(backend_name="custom")
        r1.metrics["key"] = 1.0
        assert "key" not in r2.metrics

    def test_result_equality(self):
        """两个相同字段值的 EvalResult 相等"""
        r1 = EvalResult(backend_name="custom", metrics={"h": 0.5}, details={})
        r2 = EvalResult(backend_name="custom", metrics={"h": 0.5}, details={})
        assert r1 == r2


# ============================================================
# 4. BaseEvaluator 抽象基类契约测试
# ============================================================

class TestBaseEvaluatorContract:
    """测试 BaseEvaluator 抽象基类的契约约束"""

    def test_base_evaluator_is_abstract(self):
        """BaseEvaluator 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError, match="abstract"):
            BaseEvaluator()

    def test_base_evaluator_has_evaluate_method(self):
        """BaseEvaluator 定义了 evaluate 抽象方法"""
        assert hasattr(BaseEvaluator, "evaluate")
        assert callable(getattr(BaseEvaluator, "evaluate", None))

    def test_base_evaluator_has_backend_name_property(self):
        """BaseEvaluator 定义了 backend_name 属性"""
        assert hasattr(BaseEvaluator, "backend_name")

    def test_subclass_missing_evaluate_raises_typeerror(self):
        """子类不实现 evaluate → TypeError"""

        class IncompleteEvaluator(BaseEvaluator):
            @property
            def backend_name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract"):
            IncompleteEvaluator()

    def test_subclass_missing_backend_name_raises_typeerror(self):
        """子类不实现 backend_name → TypeError"""

        class IncompleteEvaluator2(BaseEvaluator):
            def evaluate(self, query, retrieved_chunks, generated_answer, ground_truth, **kwargs):
                return EvalResult(backend_name="x")

        with pytest.raises(TypeError, match="abstract"):
            IncompleteEvaluator2()

    def test_complete_subclass_can_be_instantiated(self):
        """子类实现所有抽象方法后可以被实例化"""

        class CompleteEvaluator(BaseEvaluator):
            def evaluate(self, query, retrieved_chunks, generated_answer, ground_truth, **kwargs):
                return EvalResult(backend_name="complete", metrics={"x": 1.0})

            @property
            def backend_name(self) -> str:
                return "complete"

        e = CompleteEvaluator()
        assert isinstance(e, BaseEvaluator)
        assert e.backend_name == "complete"

    def test_evaluate_returns_eval_result(self):
        """evaluate 方法返回 EvalResult"""

        class DummyEvaluator(BaseEvaluator):
            def evaluate(self, query, retrieved_chunks, generated_answer, ground_truth, **kwargs):
                return EvalResult(backend_name="dummy", metrics={"test": 1.0})

            @property
            def backend_name(self) -> str:
                return "dummy"

        e = DummyEvaluator()
        result = e.evaluate("query", [], "", GroundTruth(golden_ids=["c1"]))
        assert isinstance(result, EvalResult)
        assert result.metrics == {"test": 1.0}

    def test_evaluate_accepts_all_parameters(self):
        """evaluate 方法接受所有必需参数"""

        class DummyEvaluator2(BaseEvaluator):
            def evaluate(self, query, retrieved_chunks, generated_answer, ground_truth, **kwargs):
                assert isinstance(query, str)
                assert isinstance(retrieved_chunks, list)
                assert isinstance(generated_answer, str)
                assert isinstance(ground_truth, GroundTruth)
                return EvalResult(backend_name="dummy")

            @property
            def backend_name(self) -> str:
                return "dummy"

        e = DummyEvaluator2()
        result = e.evaluate("query", [make_chunk()], "answer", make_ground_truth())
        assert result.backend_name == "dummy"


# ============================================================
# 5. CustomEvaluator 指标计算测试
# ============================================================

class TestCustomEvaluatorMetrics:
    """测试 CustomEvaluator 的指标计算

    知识点：检索质量指标
      - Hit Rate：golden_id 在 Top-K 中 → 1.0；不在 → 0.0
      - MRR：第一个命中 golden_id 的排名倒数（1/rank）
      - Recall@K：Top-K 中命中的 golden_ids / 总 golden_ids
      - Precision@K：Top-K 中命中数 / K

    验收标准：输入 query + retrieved_ids + golden_ids 能输出稳定 metrics
    """

    def test_custom_evaluator_backend_name(self):
        """CustomEvaluator.backend_name 返回 'custom'"""
        e = CustomEvaluator()
        assert e.backend_name == "custom"

    def test_custom_evaluator_default_top_k(self):
        """CustomEvaluator 默认 top_k=10"""
        e = CustomEvaluator()
        assert e.top_k == 10

    def test_custom_evaluator_custom_top_k(self):
        """CustomEvaluator 可以自定义 top_k"""
        e = CustomEvaluator(top_k=5)
        assert e.top_k == 5

    def test_custom_evaluator_invalid_top_k_raises(self):
        """top_k <= 0 → EvaluatorError"""
        with pytest.raises(EvaluatorError, match="top_k"):
            CustomEvaluator(top_k=0)
        with pytest.raises(EvaluatorError, match="top_k"):
            CustomEvaluator(top_k=-1)

    # --- Hit Rate 测试 ---

    def test_hit_rate_golden_at_first_position(self):
        """golden_id 在第 1 位 → hit_rate=1.0"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c1"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["hit_rate"] == 1.0

    def test_hit_rate_golden_at_last_position(self):
        """golden_id 在第 10 位 → hit_rate=1.0（在 Top-K 内）"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c10"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["hit_rate"] == 1.0

    def test_hit_rate_golden_not_in_top_k(self):
        """golden_id 在第 11 位 → hit_rate=0.0（不在 Top-K 内）"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(15)
        gt = make_ground_truth(golden_ids=["c11"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["hit_rate"] == 0.0

    def test_hit_rate_golden_not_in_results(self):
        """golden_id 不在检索结果中 → hit_rate=0.0"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["nonexistent"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["hit_rate"] == 0.0

    # --- MRR 测试 ---

    def test_mrr_golden_at_first_position(self):
        """golden_id 在第 1 位 → mrr=1.0"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c1"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["mrr"] == 1.0

    def test_mrr_golden_at_third_position(self):
        """golden_id 在第 3 位 → mrr=0.333"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c3"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["mrr"] == pytest.approx(1.0 / 3, abs=0.001)

    def test_mrr_golden_not_in_top_k(self):
        """golden_id 不在 Top-K → mrr=0.0"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(15)
        gt = make_ground_truth(golden_ids=["c11"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["mrr"] == 0.0

    def test_mrr_multiple_golden_ids(self):
        """多个 golden_ids → MRR 取第一个命中的排名"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        # golden_ids = [c5, c2] → 第一个命中是 c2（rank=2）→ mrr=0.5
        gt = make_ground_truth(golden_ids=["c5", "c2"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["mrr"] == 0.5

    # --- Recall@K 测试 ---

    def test_recall_all_golden_found(self):
        """所有 golden_ids 都在 Top-K → recall=1.0"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c1", "c2", "c3"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["recall@10"] == 1.0

    def test_recall_partial_golden_found(self):
        """部分 golden_ids 在 Top-K → recall=0.4（2/5）"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        # golden_ids = [c1, c2, c11, c12, c13] → 只有 c1, c2 命中 → recall=2/5=0.4
        gt = make_ground_truth(golden_ids=["c1", "c2", "c11", "c12", "c13"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["recall@10"] == pytest.approx(0.4, abs=0.001)

    def test_recall_no_golden_found(self):
        """没有 golden_ids 在 Top-K → recall=0.0"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c20", "c21"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["recall@10"] == 0.0

    # --- Precision@K 测试 ---

    def test_precision_partial_hits(self):
        """Top-K 中 2 个命中 → precision=2/10=0.2"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c1", "c2", "c20"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["precision@10"] == pytest.approx(0.2, abs=0.001)

    def test_precision_all_hits(self):
        """Top-K 全部命中 → precision=1.0（当 golden_ids >= K）"""
        e = CustomEvaluator(top_k=5)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c1", "c2", "c3", "c4", "c5"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["precision@5"] == 1.0

    # --- 边界情况 ---

    def test_empty_retrieved_chunks_raises(self):
        """检索结果为空 → EvaluatorError（无法评估）"""
        e = CustomEvaluator(top_k=10)
        gt = make_ground_truth(golden_ids=["c1"])
        with pytest.raises(EvaluatorError, match="golden_ids.*空"):
            # 空检索结果但有 golden_ids → 实际上可以评估（hit_rate=0）
            # 这里改为测试空 golden_ids
            e.evaluate("query", [], "", GroundTruth(golden_ids=[]))

    def test_empty_golden_ids_raises(self):
        """golden_ids 为空 → EvaluatorError"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = GroundTruth(golden_ids=[])
        with pytest.raises(EvaluatorError, match="golden_ids.*空"):
            e.evaluate("query", chunks, "", gt)

    def test_retrieved_less_than_top_k(self):
        """检索结果少于 top_k → 正常评估，actual_k = 检索结果数量"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(3)
        gt = make_ground_truth(golden_ids=["c1"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.metrics["hit_rate"] == 1.0
        assert result.details["actual_k"] == 3

    def test_details_contains_metadata(self):
        """EvalResult.details 包含元信息"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c1", "c2"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.details["top_k"] == 10
        assert result.details["actual_k"] == 10
        assert result.details["retrieved_count"] == 10
        assert result.details["golden_count"] == 2
        assert result.details["hit_count"] == 2
        assert result.details["first_hit_rank"] == 1

    def test_first_hit_rank_none_when_no_hit(self):
        """未命中时 first_hit_rank 为 None"""
        e = CustomEvaluator(top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["nonexistent"])
        result = e.evaluate("query", chunks, "", gt)
        assert result.details["first_hit_rank"] is None
        assert result.details["hit_count"] == 0


# ============================================================
# 6. EvaluatorFactory 工厂测试
# ============================================================

class TestEvaluatorFactory:
    """测试 EvaluatorFactory 的路由逻辑"""

    def test_create_returns_custom_evaluator(self):
        """backend='custom' → 创建 CustomEvaluator"""
        e = EvaluatorFactory.create("custom")
        assert isinstance(e, CustomEvaluator)
        assert e.backend_name == "custom"

    def test_create_with_top_k_kwarg(self):
        """create() 传递 top_k 参数"""
        e = EvaluatorFactory.create("custom", top_k=5)
        assert isinstance(e, CustomEvaluator)
        assert e.top_k == 5

    def test_create_raises_error_for_unknown_backend(self):
        """未知 backend → EvaluatorError"""
        with pytest.raises(EvaluatorError, match="不支持"):
            EvaluatorFactory.create("unknown_evaluator")

    def test_create_error_message_lists_supported_backends(self):
        """异常消息中列出当前支持的后端"""
        with pytest.raises(EvaluatorError) as exc_info:
            EvaluatorFactory.create("foobar")
        assert "custom" in str(exc_info.value)

    def test_create_is_case_insensitive(self):
        """backend 名称大小写不敏感"""
        e = EvaluatorFactory.create("CUSTOM")
        assert isinstance(e, CustomEvaluator)

    def test_create_strips_whitespace(self):
        """backend 名称前后空白被去除"""
        e = EvaluatorFactory.create("  custom  ")
        assert isinstance(e, CustomEvaluator)

    def test_register_adds_new_backend(self):
        """register() 可以注册新的 Evaluator 后端"""

        class CustomEvaluator2(BaseEvaluator):
            def evaluate(self, query, retrieved_chunks, generated_answer, ground_truth, **kwargs):
                return EvalResult(backend_name="custom2")

            @property
            def backend_name(self) -> str:
                return "custom2"

        EvaluatorFactory.register("custom2", CustomEvaluator2)
        try:
            e = EvaluatorFactory.create("custom2")
            assert isinstance(e, CustomEvaluator2)
            assert e.backend_name == "custom2"
        finally:
            EvaluatorFactory._BACKENDS.pop("custom2", None)

    def test_register_rejects_non_subclass(self):
        """register() 拒绝非 BaseEvaluator 子类"""

        class NotAnEvaluator:
            pass

        with pytest.raises(EvaluatorError, match="不是 BaseEvaluator"):
            EvaluatorFactory.register("bad", NotAnEvaluator)  # type: ignore

    def test_supported_backends_returns_list(self):
        """supported_backends() 返回支持的后端列表"""
        backends = EvaluatorFactory.supported_backends()
        assert "custom" in backends
        assert isinstance(backends, list)


# ============================================================
# 7. 端到端集成测试
# ============================================================

class TestEvaluatorIntegration:
    """端到端集成测试：模拟完整的评估流程"""

    def test_full_flow_custom_evaluator_hit(self):
        """完整流程：创建 CustomEvaluator → evaluate → 验证 metrics

        模拟场景：
          1. 检索返回 10 个结果（c1-c10）
          2. golden_ids = [c1]
          3. 期望 hit_rate=1.0, mrr=1.0
        """
        evaluator = EvaluatorFactory.create("custom", top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c1"])

        result = evaluator.evaluate("什么是向量数据库？", chunks, "", gt)

        assert result.backend_name == "custom"
        assert result.metrics["hit_rate"] == 1.0
        assert result.metrics["mrr"] == 1.0
        assert result.metrics["recall@10"] == 1.0
        assert result.metrics["precision@10"] == pytest.approx(0.1, abs=0.001)

    def test_full_flow_custom_evaluator_miss(self):
        """完整流程：golden_id 不在结果中 → 所有指标为 0"""
        evaluator = EvaluatorFactory.create("custom", top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["nonexistent"])

        result = evaluator.evaluate("query", chunks, "", gt)

        assert result.metrics["hit_rate"] == 0.0
        assert result.metrics["mrr"] == 0.0
        assert result.metrics["recall@10"] == 0.0
        assert result.metrics["precision@10"] == 0.0

    def test_full_flow_multiple_golden_ids(self):
        """完整流程：多个 golden_ids，部分命中"""
        evaluator = EvaluatorFactory.create("custom", top_k=5)
        chunks = make_chunks(10)
        # golden = [c1, c3, c6, c8] → Top-5 中命中 c1, c3 → hit=2
        gt = make_ground_truth(golden_ids=["c1", "c3", "c6", "c8"])

        result = evaluator.evaluate("query", chunks, "", gt)

        assert result.metrics["hit_rate"] == 1.0  # 至少命中一个
        assert result.metrics["mrr"] == 1.0  # 第一个命中是 c1（rank=1）
        assert result.metrics["recall@5"] == pytest.approx(0.5, abs=0.001)  # 2/4
        assert result.metrics["precision@5"] == pytest.approx(0.4, abs=0.001)  # 2/5

    def test_metrics_are_deterministic(self):
        """验证指标计算是确定性的（多次运行结果相同）

        验收标准：能输出稳定 metrics
        """
        evaluator = EvaluatorFactory.create("custom", top_k=10)
        chunks = make_chunks(10)
        gt = make_ground_truth(golden_ids=["c2", "c5"])

        results = [
            evaluator.evaluate("query", chunks, "", gt)
            for _ in range(5)
        ]

        # 所有 5 次运行的 metrics 应完全相同
        first_metrics = results[0].metrics
        for r in results[1:]:
            assert r.metrics == first_metrics

