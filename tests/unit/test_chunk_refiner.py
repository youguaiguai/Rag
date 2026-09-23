"""
ChunkRefiner 单元测试 — C5: Transform 抽象基类 + ChunkRefiner

测试策略：
  - 使用 MockLLM（自定义可编程桩）隔离，不依赖真实 API
  - 使用 noisy_chunks.json fixtures 驱动规则去噪测试
  - 验收标准全覆盖：
    1. 规则模式：对 fixtures 噪声样例能正确去噪
    2. 保留能力：代码块内部格式不破坏，Markdown 结构完整保留
    3. LLM 模式：mock LLM 时能正确调用并返回重写结果，refined_by="llm"
    4. 降级行为：LLM 失败时回退到规则结果，refined_by="rule" + fallback 原因
    5. 配置开关：use_llm 控制是否调用 LLM
    6. 异常处理：单个 chunk 处理异常不影响其他 chunk，保留原文

测试分类（27 个）：
  - BaseTransform ABC 契约（3）
  - TraceContext（3）
  - 规则去噪 fixtures 驱动（8）
  - 保留能力（2）
  - LLM 模式（3）
  - 降级行为（3）
  - 配置开关 + settings（3）
  - Prompt 加载（1，参数化 2 用例）
  - 异常隔离（1）
"""

from __future__ import annotations

import json
import pytest
from core.settings import Settings, LLMSettings, ChunkRefinerSettings, IngestionSettings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.base_transform import BaseTransform, TransformError
from ingestion.transform.chunk_refiner import ChunkRefiner
from libs.llm.base_llm import BaseLLM, LLMError, MessageType
from pathlib import Path
from typing import Any


# ============================================================
# MockLLM — 可编程测试桩
# ============================================================

class MockLLM(BaseLLM):
    """可编程 Mock LLM — 记录调用 + 可配置返回值/异常

    知识点：Mock vs Stub
      - Stub（桩）：返回固定值（如 FakeLLM）
      - Mock（模拟对象）：记录调用 + 可配置行为 + 可验证调用次数
      - 面试考点："Mock 和 Stub 的区别？" → Mock 有验证能力
    """

    def __init__(
        self,
        response: str = "mock refined text",
        error: Exception | None = None,
    ) -> None:
        self._model_name = "mock-model"
        self._response = response
        self._error = error
        self.calls: list[list[dict[str, str]]] = []  # 记录每次调用的 messages

    def chat(self, messages: list[MessageType], **kwargs: Any) -> str:
        self.calls.append(messages)  # type: ignore[arg-type]
        if self._error is not None:
            raise self._error
        return self._response

    @property
    def model_name(self) -> str:
        return self._model_name


# ============================================================
# 辅助函数
# ============================================================

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "noisy_chunks.json"
PROMPT_PATH = Path(__file__).parent.parent.parent / "config" / "prompts" / "chunk_refinement.txt"


def _make_settings(use_llm: bool = False, prompt_path: str | None = None) -> Settings:
    """创建测试用 Settings"""
    s = Settings()
    s.ingestion.chunk_refiner.use_llm = use_llm
    if prompt_path is not None:
        s.ingestion.chunk_refiner.prompt_path = prompt_path
    return s


def _make_chunk(text: str, chunk_id: str = "c_0001", index: int = 0,
                 metadata: dict[str, Any] | None = None) -> Chunk:
    """创建测试用 Chunk"""
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc123",
        text=text,
        index=index,
        source_ref=f"/test.md#chunk={index}",
        metadata=metadata or {},
    )


def _load_fixtures() -> dict[str, dict[str, Any]]:
    """加载 noisy_chunks.json fixtures"""
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# BaseTransform ABC 契约（3 个）
# ============================================================

class TestBaseTransformABC:
    """BaseTransform 抽象基类契约测试"""

    def test_cannot_instantiate_base_transform(self):
        """ABC 不可实例化"""
        with pytest.raises(TypeError):
            BaseTransform()  # type: ignore[abstract]

    def test_subclass_missing_transform_raises(self):
        """子类未实现 transform → TypeError"""
        class IncompleteTransform(BaseTransform):
            pass

        with pytest.raises(TypeError):
            IncompleteTransform()  # type: ignore[abstract]

    def test_subclass_full_implementation_works(self):
        """完整实现 → 可实例化且可用"""
        class IdentityTransform(BaseTransform):
            def transform(self, chunks, trace=None):
                return chunks

        t = IdentityTransform()
        chunk = _make_chunk("hello")
        result = t.transform([chunk])
        assert len(result) == 1
        assert result[0].text == "hello"


# ============================================================
# TraceContext（3 个）
# ============================================================

class TestTraceContext:

    def test_trace_id_unique(self):
        """自动生成的 trace_id 唯一"""
        t1 = TraceContext()
        t2 = TraceContext()
        assert t1.trace_id != t2.trace_id
        assert len(t1.trace_id) > 0

    def test_record_stage_stores_data(self):
        """record_stage 存储阶段数据"""
        trace = TraceContext()
        trace.record_stage("chunk_refiner", {"count": 5}, duration_ms=12.3)
        stages = trace.get_stages("chunk_refiner")
        assert len(stages) == 1
        assert stages[0].data["count"] == 5
        assert stages[0].duration_ms == 12.3

    def test_finish_returns_summary(self):
        """finish + to_dict 返回可序列化汇总 dict"""
        trace = TraceContext(trace_id="test-trace-123")
        trace.record_stage("loader", {"path": "/doc.md"})
        trace.record_stage("chunker", {"count": 3}, duration_ms=5.0)

        trace.finish()
        summary = trace.to_dict()

        assert summary["trace_id"] == "test-trace-123"
        assert len(summary["stages"]) == 2
        assert summary["stages"][0]["stage"] == "loader"
        assert summary["stages"][1]["data"]["count"] == 3
        assert "total_elapsed_ms" in summary


# ============================================================
# 规则去噪 fixtures 驱动（8 个）
# ============================================================

class TestRuleBasedRefine:
    """规则去噪测试 — 使用 noisy_chunks.json fixtures"""

    @pytest.fixture
    def refiner(self) -> ChunkRefiner:
        """纯规则模式 ChunkRefiner"""
        return ChunkRefiner(_make_settings(use_llm=False))

    @pytest.mark.parametrize("scenario_name", [
        "typical_noise_scenario",
        "ocr_errors",
        "page_header_footer",
        "excessive_whitespace",
        "format_markers",
        "clean_text",
        "code_blocks",
        "mixed_noise",
    ])
    def test_scenario(self, refiner: ChunkRefiner, scenario_name: str):
        """对每个噪声场景：去噪后包含期望内容，不包含噪声内容"""
        fixtures = _load_fixtures()
        scenario = fixtures[scenario_name]
        input_text = scenario["input"]
        expected_contains = scenario["expected_contains"]
        expected_absent = scenario["expected_absent"]

        # 对 Chunk 执行规则去噪
        chunk = _make_chunk(input_text)
        result = refiner.transform([chunk])

        assert len(result) == 1
        refined_text = result[0].text

        # 断言期望内容存在
        for expected in expected_contains:
            assert expected in refined_text, (
                f"[{scenario_name}] 期望包含 '{expected}'，但实际：{refined_text!r}"
            )

        # 断言噪声内容已去除
        for absent in expected_absent:
            assert absent not in refined_text, (
                f"[{scenario_name}] 期望去除 '{absent}'，但实际：{refined_text!r}"
            )


# ============================================================
# 保留能力（2 个）
# ============================================================

class TestPreservation:

    def test_markdown_structure_preserved(self):
        """Markdown 结构（标题/列表/粗体）完整保留"""
        text = (
            "# 标题\n\n"
            "## 子标题\n\n"
            "- 列表项 1\n"
            "- 列表项 2\n\n"
            "**粗体文本** 和 *斜体文本*\n\n"
            "[链接](https://example.com)"
        )
        refiner = ChunkRefiner(_make_settings(use_llm=False))
        chunk = _make_chunk(text)
        result = refiner.transform([chunk])

        refined = result[0].text
        assert "# 标题" in refined
        assert "## 子标题" in refined
        assert "- 列表项 1" in refined
        assert "**粗体文本**" in refined
        assert "[链接](https://example.com)" in refined

    def test_image_placeholder_preserved(self):
        """[IMAGE: id] 占位符不受空白规则影响"""
        text = (
            "图片说明文字。\n\n"
            "[IMAGE: img_001]\n\n"
            "更多文字。"
        )
        refiner = ChunkRefiner(_make_settings(use_llm=False))
        chunk = _make_chunk(text)
        result = refiner.transform([chunk])

        assert "[IMAGE: img_001]" in result[0].text


# ============================================================
# LLM 模式（3 个）
# ============================================================

class TestLLMMode:

    def test_llm_refine_success(self):
        """mock LLM 成功 → refined_by='llm'"""
        mock_llm = MockLLM(response="这是 LLM 清洗后的文本。")
        refiner = ChunkRefiner(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("一些带有   噪声的文本。")
        result = refiner.transform([chunk])

        assert result[0].text == "这是 LLM 清洗后的文本。"
        assert result[0].metadata["refined_by"] == "llm"
        assert len(mock_llm.calls) == 1  # LLM 被调用一次

    def test_llm_receives_rule_cleaned_text(self):
        """LLM 拿到的是规则去噪后的文本（不含页码等噪声）"""
        mock_llm = MockLLM(response="refined")
        refiner = ChunkRefiner(_make_settings(use_llm=True), llm=mock_llm)

        text = "正文内容。\n\n第 5 页\n\n更多内容。"
        chunk = _make_chunk(text)
        refiner.transform([chunk])

        # 验证 LLM 收到的 user message 不含 "第 5 页"
        user_msg = mock_llm.calls[0][-1]["content"]
        assert "第 5 页" not in user_msg
        assert "正文内容。" in user_msg
        assert "更多内容。" in user_msg

    def test_llm_empty_response_fallback(self):
        """LLM 返回空 → 降级到规则结果"""
        mock_llm = MockLLM(response="   ")  # 纯空白
        refiner = ChunkRefiner(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("正常文本内容。")
        result = refiner.transform([chunk])

        # 降级到规则结果
        assert result[0].metadata["refined_by"] == "rule"
        assert result[0].metadata["refinement_fallback"] == "llm_empty_response"
        assert result[0].text == "正常文本内容。"  # 规则清理后的文本


# ============================================================
# 降级行为（3 个）
# ============================================================

class TestFallback:

    def test_llm_error_fallback_with_reason(self):
        """LLMError → 规则结果 + refined_by='rule' + fallback 原因"""
        mock_llm = MockLLM(error=LLMError("Connection timeout"))
        refiner = ChunkRefiner(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("重要业务文本。")
        result = refiner.transform([chunk])

        assert result[0].metadata["refined_by"] == "rule"
        reason = result[0].metadata["refinement_fallback"]
        assert "llm_error" in reason
        assert "Connection timeout" in reason

    def test_llm_unexpected_error_fallback(self):
        """意外异常（非 LLMError）→ 也降级到规则结果"""
        mock_llm = MockLLM(error=RuntimeError("unexpected"))
        refiner = ChunkRefiner(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("文本内容。")
        result = refiner.transform([chunk])

        assert result[0].metadata["refined_by"] == "rule"
        reason = result[0].metadata["refinement_fallback"]
        assert "llm_unexpected_error" in reason

    def test_llm_factory_failure_degrades_to_rule(self):
        """LLM 工厂创建失败（provider 无效）→ 自动降级为纯规则模式"""
        settings = _make_settings(use_llm=True)
        # LLMSettings 默认 provider="" → LLMFactory.create 抛异常 → 降级
        refiner = ChunkRefiner(settings)

        assert refiner.use_llm is False  # 降级后关闭

        chunk = _make_chunk("文本内容。")
        result = refiner.transform([chunk])
        assert result[0].metadata["refined_by"] == "rule"


# ============================================================
# 配置开关 + settings（3 个）
# ============================================================

class TestConfigSwitch:

    def test_use_llm_false_skips_llm(self):
        """use_llm=False → 不调用 LLM"""
        mock_llm = MockLLM(response="should not be used")
        refiner = ChunkRefiner(_make_settings(use_llm=False), llm=mock_llm)

        chunk = _make_chunk("正常文本。")
        result = refiner.transform([chunk])

        assert len(mock_llm.calls) == 0  # LLM 从未被调用
        assert result[0].metadata["refined_by"] == "rule"

    def test_use_llm_true_calls_llm(self):
        """use_llm=True → 调用 LLM"""
        mock_llm = MockLLM(response="llm refined")
        refiner = ChunkRefiner(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("文本。")
        refiner.transform([chunk])

        assert len(mock_llm.calls) == 1  # LLM 被调用

    def test_settings_yaml_loads_ingestion(self):
        """settings.yaml 的 ingestion.chunk_refiner 配置加载正确"""
        from core.settings import load_settings
        settings = load_settings("config/settings.yaml")

        assert hasattr(settings, "ingestion")
        assert hasattr(settings.ingestion, "chunk_refiner")
        assert settings.ingestion.chunk_refiner.use_llm is False
        assert "chunk_refinement.txt" in settings.ingestion.chunk_refiner.prompt_path


# ============================================================
# Prompt 加载（1 个，参数化 2 用例）
# ============================================================

class TestPromptLoading:

    @pytest.mark.parametrize("scenario, path_exists, check", [
        ("from_file", True, lambda tmpl: "{text}" in tmpl),
        ("fallback_default", False, lambda tmpl: "{text}" in tmpl),
    ])
    def test_prompt_loading(self, scenario: str, path_exists: bool, check):
        """prompt 加载：文件存在用文件内容，不存在用内置默认"""
        if path_exists:
            # 使用真实 prompt 文件
            refiner = ChunkRefiner(
                _make_settings(use_llm=False),
                prompt_path=str(PROMPT_PATH),
            )
        else:
            # 指向不存在的文件 → fallback
            refiner = ChunkRefiner(
                _make_settings(use_llm=False),
                prompt_path="/nonexistent/prompt.txt",
            )

        assert check(refiner.prompt_template)
        assert "{text}" in refiner.prompt_template


# ============================================================
# 异常隔离（1 个）
# ============================================================

class TestExceptionIsolation:

    def test_single_chunk_exception_isolated(self, monkeypatch):
        """单个 chunk 处理异常 → 保留原文 + metadata 标记，不影响其他 chunk"""
        refiner = ChunkRefiner(_make_settings(use_llm=False))

        # 让 _rule_based_refine 在特定输入时抛异常
        original_refine = refiner._rule_based_refine
        call_count = {"n": 0}

        def flaky_refine(text: str) -> str:
            call_count["n"] += 1
            if "BOOM" in text:
                raise RuntimeError("simulated processing error")
            return original_refine(text)

        monkeypatch.setattr(refiner, "_rule_based_refine", flaky_refine)

        chunks = [
            _make_chunk("正常 chunk A。", chunk_id="c_0001", index=0),
            _make_chunk("BOOM", chunk_id="c_0002", index=1),
            _make_chunk("正常 chunk B。", chunk_id="c_0003", index=2),
        ]

        result = refiner.transform(chunks)

        # 三个 chunk 都返回
        assert len(result) == 3
        # 第一个正常
        assert result[0].metadata["refined_by"] == "rule"
        # 第二个异常 → 保留原文 + refined_by="error"
        assert "BOOM" in result[1].text  # 保留原文
        assert result[1].metadata["refined_by"] == "error"
        assert "exception" in result[1].metadata["refinement_fallback"]
        # 第三个正常（异常隔离）
        assert result[2].metadata["refined_by"] == "rule"

