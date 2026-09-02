"""
MetadataEnricher 单元测试 — C6: 规则增强 + 可选 LLM 增强 + 降级

测试策略：
  - 使用 MockLLM 隔离，不依赖真实 API
  - 验收标准全覆盖：
    1. 规则模式：metadata 必须包含 title/summary/tags（非空）
    2. LLM 模式：mock LLM 时生成语义丰富的 metadata，enriched_by="llm"
    3. 降级行为：LLM 失败回退到规则结果，enriched_by="rule"
    4. 配置开关：use_llm 控制行为
    5. 异常处理：单个 chunk 异常不影响其他 chunk

测试分类（22 个）：
  - BaseTransform 继承（2）
  - 规则模式 title/summary/tags（5）
  - 规则模式边界（3）
  - LLM 模式（3）
  - LLM 响应解析（3）
  - 降级行为（3）
  - 配置开关（2）
  - 异常隔离 + prompt 加载（1，参数化）
"""

from __future__ import annotations

import json
import pytest
from core.settings import Settings, MetadataEnricherSettings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.base_transform import BaseTransform, TransformError
from ingestion.transform.metadata_enricher import MetadataEnricher
from libs.llm.base_llm import BaseLLM, LLMError, MessageType
from pathlib import Path
from typing import Any


# ============================================================
# MockLLM — 可编程测试桩
# ============================================================

class MockLLM(BaseLLM):
    """可编程 Mock LLM — 记录调用 + 可配置返回值/异常"""

    def __init__(
        self,
        response: str = '{"title": "mock", "summary": "mock summary", "tags": ["tag1", "tag2"]}',
        error: Exception | None = None,
    ) -> None:
        self._model_name = "mock-model"
        self._response = response
        self._error = error
        self.calls: list[list[dict[str, str]]] = []

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

PROMPT_PATH = Path(__file__).parent.parent.parent / "config" / "prompts" / "metadata_enrichment.txt"


def _make_settings(use_llm: bool = False, max_tags: int = 5, prompt_path: str | None = None) -> Settings:
    """创建测试用 Settings"""
    s = Settings()
    s.ingestion.metadata_enricher.use_llm = use_llm
    s.ingestion.metadata_enricher.max_tags = max_tags
    if prompt_path is not None:
        s.ingestion.metadata_enricher.prompt_path = prompt_path
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


# ============================================================
# BaseTransform 继承（2 个）
# ============================================================

class TestInheritance:

    def test_is_base_transform(self):
        """MetadataEnricher 是 BaseTransform 的子类"""
        enricher = MetadataEnricher(_make_settings())
        assert isinstance(enricher, BaseTransform)

    def test_transform_signature(self):
        """transform 方法签名正确"""
        enricher = MetadataEnricher(_make_settings())
        chunk = _make_chunk("测试文本")
        result = enricher.transform([chunk])
        assert isinstance(result, list)
        assert len(result) == 1


# ============================================================
# 规则模式 title/summary/tags（5 个）
# ============================================================

class TestRuleBasedEnrichment:

    @pytest.fixture
    def enricher(self) -> MetadataEnricher:
        return MetadataEnricher(_make_settings(use_llm=False))

    def test_title_from_markdown_heading(self, enricher: MetadataEnricher):
        """title: 从 Markdown 标题提取"""
        text = "# 系统架构设计\n\n本系统采用模块化设计。"
        chunk = _make_chunk(text)
        result = enricher.transform([chunk])

        assert result[0].metadata["title"] == "系统架构设计"
        assert result[0].metadata["enriched_by"] == "rule"

    def test_title_from_first_line_when_no_heading(self, enricher: MetadataEnricher):
        """title: 无标题时从首行提取"""
        text = "这是一个没有标题的文档片段。\n\n第二行内容。"
        chunk = _make_chunk(text)
        result = enricher.transform([chunk])

        assert result[0].metadata["title"] == "这是一个没有标题的文档片段。"

    def test_summary_truncated_to_sentence_boundary(self, enricher: MetadataEnricher):
        """summary: 截断到句子边界"""
        long_text = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。" * 10
        chunk = _make_chunk(long_text)
        result = enricher.transform([chunk])

        summary = result[0].metadata["summary"]
        assert len(summary) <= 100 + 10  # 允许句子边界偏移
        assert "。" in summary  # 应在句子边界截断

    def test_tags_extracted_from_text(self, enricher: MetadataEnricher):
        """tags: 从文本提取关键词"""
        text = "向量数据库是 RAG 系统的核心组件。向量数据库支持相似度检索。"
        chunk = _make_chunk(text)
        result = enricher.transform([chunk])

        tags = result[0].metadata["tags"]
        assert isinstance(tags, list)
        assert len(tags) > 0
        assert len(tags) <= 5
        # 规则模式提取的是连续 CJK 字符段（非语义分词），
        # "向量数据库" 出现两次，tags 中应有一个包含该子串的项
        assert any("向量数据库" in t for t in tags), f"tags 中应包含'向量数据库'相关词，实际：{tags}"

    def test_metadata_has_all_three_fields(self, enricher: MetadataEnricher):
        """metadata 必须包含 title/summary/tags 三个字段"""
        text = "# 标题\n\n内容文本。"
        chunk = _make_chunk(text)
        result = enricher.transform([chunk])

        meta = result[0].metadata
        assert "title" in meta
        assert "summary" in meta
        assert "tags" in meta
        assert meta["title"]  # 非空
        assert meta["summary"]  # 非空
        assert isinstance(meta["tags"], list)


# ============================================================
# 规则模式边界（3 个）
# ============================================================

class TestRuleBasedEdgeCases:

    def test_empty_text(self):
        """空文本 → title/summary/tags 有兜底值"""
        enricher = MetadataEnricher(_make_settings(use_llm=False))
        chunk = _make_chunk("")
        result = enricher.transform([chunk])

        meta = result[0].metadata
        assert meta["title"]  # 有兜底值
        assert isinstance(meta["tags"], list)

    def test_short_text_summary_is_full_text(self):
        """短文本 summary = 全文"""
        enricher = MetadataEnricher(_make_settings(use_llm=False))
        text = "短文本。"
        chunk = _make_chunk(text)
        result = enricher.transform([chunk])

        assert result[0].metadata["summary"] == "短文本。"

    def test_max_tags_limit(self):
        """tags 数量不超过 max_tags"""
        enricher = MetadataEnricher(_make_settings(use_llm=False, max_tags=3))
        text = "数据库 检索 向量 嵌入 模型 算法 系统 架构 设计 模块"
        chunk = _make_chunk(text)
        result = enricher.transform([chunk])

        assert len(result[0].metadata["tags"]) <= 3


# ============================================================
# LLM 模式（3 个）
# ============================================================

class TestLLMMode:

    def test_llm_enrich_success(self):
        """mock LLM 成功 → enriched_by='llm'"""
        llm_response = json.dumps({
            "title": "LLM 生成的标题",
            "summary": "这是 LLM 生成的摘要。",
            "tags": ["tag1", "tag2", "tag3"],
        })
        mock_llm = MockLLM(response=llm_response)
        enricher = MetadataEnricher(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("一些文本内容。")
        result = enricher.transform([chunk])

        assert result[0].metadata["enriched_by"] == "llm"
        assert result[0].metadata["title"] == "LLM 生成的标题"
        assert result[0].metadata["summary"] == "这是 LLM 生成的摘要。"
        assert result[0].metadata["tags"] == ["tag1", "tag2", "tag3"]
        assert len(mock_llm.calls) == 1

    def test_llm_tags_truncated_to_max(self):
        """LLM 返回的 tags 超过 max_tags 时截断"""
        llm_response = json.dumps({
            "title": "标题",
            "summary": "摘要",
            "tags": ["a", "b", "c", "d", "e", "f", "g"],
        })
        mock_llm = MockLLM(response=llm_response)
        enricher = MetadataEnricher(_make_settings(use_llm=True, max_tags=3), llm=mock_llm)

        chunk = _make_chunk("文本")
        result = enricher.transform([chunk])

        assert len(result[0].metadata["tags"]) == 3

    def test_llm_missing_fields_fallback_to_rule(self):
        """LLM 返回缺少字段 → 用规则结果补"""
        llm_response = json.dumps({"title": "只有标题"})
        mock_llm = MockLLM(response=llm_response)
        enricher = MetadataEnricher(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("# 规则标题\n\n规则内容文本。")
        result = enricher.transform([chunk])

        assert result[0].metadata["enriched_by"] == "llm"
        assert result[0].metadata["title"] == "只有标题"  # LLM 的
        assert result[0].metadata["summary"]  # 规则的兜底
        assert isinstance(result[0].metadata["tags"], list)


# ============================================================
# LLM 响应解析（3 个）
# ============================================================

class TestLLMResponseParsing:

    def test_parse_plain_json(self):
        """直接 JSON 解析"""
        enricher = MetadataEnricher(_make_settings(use_llm=False))
        response = '{"title": "t", "summary": "s", "tags": ["a"]}'
        result = enricher._parse_llm_response(response)
        assert result is not None
        assert result["title"] == "t"

    def test_parse_json_with_surrounding_text(self):
        """JSON 前后有文字 → 提取 JSON 块"""
        enricher = MetadataEnricher(_make_settings(use_llm=False))
        response = '好的，以下是结果：\n{"title": "t", "summary": "s", "tags": ["a"]}\n以上。'
        result = enricher._parse_llm_response(response)
        assert result is not None
        assert result["title"] == "t"

    def test_parse_invalid_json_returns_none(self):
        """无效 JSON → 返回 None"""
        enricher = MetadataEnricher(_make_settings(use_llm=False))
        response = '这不是 JSON 格式'
        result = enricher._parse_llm_response(response)
        assert result is None


# ============================================================
# 降级行为（3 个）
# ============================================================

class TestFallback:

    def test_llm_error_fallback_to_rule(self):
        """LLMError → 规则结果 + enriched_by='rule' + fallback 原因"""
        mock_llm = MockLLM(error=LLMError("timeout"))
        enricher = MetadataEnricher(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("# 标题\n\n内容。")
        result = enricher.transform([chunk])

        assert result[0].metadata["enriched_by"] == "rule"
        assert "llm_error" in result[0].metadata["enrichment_fallback"]
        assert result[0].metadata["title"] == "标题"

    def test_llm_empty_response_fallback(self):
        """LLM 返回空 → 降级"""
        mock_llm = MockLLM(response="  ")
        enricher = MetadataEnricher(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("# 标题\n\n内容。")
        result = enricher.transform([chunk])

        assert result[0].metadata["enriched_by"] == "rule"
        assert result[0].metadata["enrichment_fallback"] == "llm_empty_response"

    def test_llm_invalid_json_fallback(self):
        """LLM 返回非 JSON → 降级"""
        mock_llm = MockLLM(response="这不是JSON")
        enricher = MetadataEnricher(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("# 标题\n\n内容。")
        result = enricher.transform([chunk])

        assert result[0].metadata["enriched_by"] == "rule"
        assert result[0].metadata["enrichment_fallback"] == "llm_json_parse_error"
        # 规则结果仍然有效
        assert result[0].metadata["title"] == "标题"


# ============================================================
# 配置开关（2 个）
# ============================================================

class TestConfigSwitch:

    def test_use_llm_false_skips_llm(self):
        """use_llm=False → 不调用 LLM"""
        mock_llm = MockLLM()
        enricher = MetadataEnricher(_make_settings(use_llm=False), llm=mock_llm)

        chunk = _make_chunk("文本")
        enricher.transform([chunk])

        assert len(mock_llm.calls) == 0

    def test_use_llm_true_calls_llm(self):
        """use_llm=True → 调用 LLM"""
        mock_llm = MockLLM(response='{"title":"t","summary":"s","tags":["a"]}')
        enricher = MetadataEnricher(_make_settings(use_llm=True), llm=mock_llm)

        chunk = _make_chunk("文本")
        enricher.transform([chunk])

        assert len(mock_llm.calls) == 1


# ============================================================
# 异常隔离 + prompt 加载 + settings（2 个）
# ============================================================

class TestExceptionAndPrompt:

    def test_single_chunk_exception_isolated(self, monkeypatch):
        """单个 chunk 处理异常 → 保留原文 + metadata 标记"""
        enricher = MetadataEnricher(_make_settings(use_llm=False))

        original = enricher._rule_based_enrich

        def flaky_enrich(text: str) -> dict[str, Any]:
            if "BOOM" in text:
                raise RuntimeError("simulated error")
            return original(text)

        monkeypatch.setattr(enricher, "_rule_based_enrich", flaky_enrich)

        chunks = [
            _make_chunk("正常 chunk。", chunk_id="c1", index=0),
            _make_chunk("BOOM", chunk_id="c2", index=1),
            _make_chunk("另一个正常。", chunk_id="c3", index=2),
        ]
        result = enricher.transform(chunks)

        assert len(result) == 3
        assert result[0].metadata["enriched_by"] == "rule"
        assert result[1].metadata["enriched_by"] == "error"
        assert "exception" in result[1].metadata["enrichment_fallback"]
        assert result[2].metadata["enriched_by"] == "rule"

    @pytest.mark.parametrize("scenario, path_exists", [
        ("from_file", True),
        ("fallback_default", False),
    ])
    def test_prompt_loading(self, scenario: str, path_exists: bool):
        """prompt 加载：文件存在用文件，不存在用内置默认"""
        if path_exists:
            enricher = MetadataEnricher(
                _make_settings(use_llm=False),
                prompt_path=str(PROMPT_PATH),
            )
        else:
            enricher = MetadataEnricher(
                _make_settings(use_llm=False),
                prompt_path="/nonexistent/prompt.txt",
            )
        assert "{text}" in enricher.prompt_template


# ============================================================
# Trace + Settings 集成（1 个）
# ============================================================

class TestTraceAndSettings:

    def test_settings_yaml_loads_metadata_enricher(self):
        """settings.yaml 的 ingestion.metadata_enricher 配置加载正确"""
        from core.settings import load_settings
        settings = load_settings("config/settings.yaml")

        assert hasattr(settings.ingestion, "metadata_enricher")
        assert settings.ingestion.metadata_enricher.use_llm is False
        assert settings.ingestion.metadata_enricher.max_tags == 5

    def test_trace_records_stage(self):
        """trace 上下文记录阶段数据"""
        enricher = MetadataEnricher(_make_settings(use_llm=False))
        trace = TraceContext(trace_id="test-enricher")

        chunk = _make_chunk("# 标题\n\n内容。")
        enricher.transform([chunk], trace=trace)

        stages = trace.get_stages("metadata_enricher")
        assert len(stages) == 1
        assert stages[0].data["total"] == 1
        assert stages[0].data["use_llm"] is False

