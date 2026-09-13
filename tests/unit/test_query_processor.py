"""
QueryProcessor 单元测试 — D1: 关键词提取 + filters 解析

测试策略：
  - 纯本地计算，无需 Mock 外部 API
  - 验收标准全覆盖：
    1. 关键词提取：对输入 query 输出 keywords 非空（根据停用词策略）
    2. filters 解析：filters 为 dict（None → {}, dict → 原样返回）
    3. 异常处理：空查询抛 ValueError
    4. Trace 支持：process 可选记录 trace
    5. ProcessedQuery 数据契约：raw_query/keywords/filters 字段正确

测试分类（28 个）：
  - ProcessedQuery 数据契约（4）
  - 英文关键词提取（5）
  - 中文关键词提取（4）
  - 混合文本关键词提取（3）
  - 停用词过滤（3）
  - 去重逻辑（2）
  - filters 解析（4）
  - 异常处理（2）
  - Trace 集成（1，参数化 2 用例）
"""

from __future__ import annotations

import pytest
from core.query_engine.query_processor import QueryProcessor
from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import ProcessedQuery
from typing import Any


# ============================================================
# 辅助函数
# ============================================================

def _make_settings() -> Settings:
    """创建测试用 Settings（默认配置即可，QueryProcessor 不需要额外配置）"""
    return Settings()


def _make_processor() -> QueryProcessor:
    """创建测试用 QueryProcessor"""
    return QueryProcessor(_make_settings())


# ============================================================
# TestProcessedQueryContract — ProcessedQuery 数据契约验证
# ============================================================

class TestProcessedQueryContract:
    """ProcessedQuery 数据契约验证（4 个测试）

    知识点：ProcessedQuery 是检索链路的"数据契约"
      - raw_query: 原始查询（DenseRetriever 用于 embedding）
      - keywords: 关键词列表（SparseRetriever 用于 BM25）
      - filters: 过滤条件 dict（HybridSearch 用于 metadata 过滤）
    """

    def test_processed_query_has_raw_query_field(self) -> None:
        """ProcessedQuery 必须包含 raw_query 字段"""
        result = ProcessedQuery(raw_query="test query")
        assert hasattr(result, "raw_query")
        assert result.raw_query == "test query"

    def test_processed_query_has_keywords_field(self) -> None:
        """ProcessedQuery 必须包含 keywords 字段，默认空列表"""
        result = ProcessedQuery(raw_query="test")
        assert hasattr(result, "keywords")
        assert isinstance(result.keywords, list)
        assert result.keywords == []

    def test_processed_query_has_filters_field(self) -> None:
        """ProcessedQuery 必须包含 filters 字段，默认空 dict"""
        result = ProcessedQuery(raw_query="test")
        assert hasattr(result, "filters")
        assert isinstance(result.filters, dict)
        assert result.filters == {}

    def test_processed_query_all_fields(self) -> None:
        """ProcessedQuery 所有字段可正确赋值"""
        result = ProcessedQuery(
            raw_query="how to use python",
            keywords=["python"],
            filters={"doc_type": "md"},
        )
        assert result.raw_query == "how to use python"
        assert result.keywords == ["python"]
        assert result.filters == {"doc_type": "md"}


# ============================================================
# TestEnglishKeywordExtraction — 英文关键词提取
# ============================================================

class TestEnglishKeywordExtraction:
    """英文关键词提取测试（5 个测试）

    知识点：英文分词策略
      - 正则 [a-zA-Z]{3,} 提取 3+ 字母词
      - 小写化统一
      - 去停用词（the/a/is/...）
    """

    def test_simple_english_query(self) -> None:
        """简单英文查询提取关键词"""
        processor = _make_processor()
        result = processor.process("machine learning algorithms")
        assert isinstance(result, ProcessedQuery)
        assert len(result.keywords) > 0
        assert "machine" in result.keywords
        assert "learning" in result.keywords
        assert "algorithms" in result.keywords

    def test_english_with_short_words_filtered(self) -> None:
        """3 字母以下词被过滤"""
        processor = _make_processor()
        result = processor.process("go to the store and buy food")
        # "go", "to", "the", "and" 等短词/停用词被过滤
        assert "store" in result.keywords
        assert "buy" in result.keywords  # "buy" 有 3 字母，匹配 {3,} 正则，不是停用词
        assert "food" in result.keywords
        assert "the" not in result.keywords
        assert "and" not in result.keywords

    def test_case_insensitive_extraction(self) -> None:
        """关键词提取不区分大小写，统一小写化"""
        processor = _make_processor()
        result = processor.process("Python Machine Learning")
        assert "python" in result.keywords
        assert "machine" in result.keywords
        assert "learning" in result.keywords
        # 所有关键词应是小写
        for kw in result.keywords:
            assert kw == kw.lower()

    def test_query_with_numbers_and_punctuation(self) -> None:
        """含数字和标点的查询只提取纯字母词"""
        processor = _make_processor()
        result = processor.process("What is Python 3.12? Show me the code!")
        # "what" 是停用词，应被过滤
        assert "what" not in result.keywords
        assert "python" in result.keywords
        assert "show" in result.keywords
        assert "code" in result.keywords

    def test_keywords_non_empty_guarantee(self) -> None:
        """验收标准：对输入 query 输出 keywords 非空"""
        processor = _make_processor()
        result = processor.process("retrieval augmented generation systems")
        assert len(result.keywords) > 0
        assert isinstance(result.keywords, list)


# ============================================================
# TestChineseKeywordExtraction — 中文关键词提取
# ============================================================

class TestChineseKeywordExtraction:
    """中文关键词提取测试（4 个测试）

    知识点：中文分词策略
      - Bigram（2-gram）策略，无需 jieba
      - 连续中文字符两两组合
      - 面试考点："为什么用 bigram？" → 减少外部依赖，BM25 统计足够
    """

    def test_simple_chinese_query(self) -> None:
        """简单中文查询提取 bigram 关键词"""
        processor = _make_processor()
        result = processor.process("向量数据库检索")
        assert len(result.keywords) > 0
        # "向量数据库检索" → bigrams: "向量", "量数", "数据", "据库", "库检", "检索"
        assert "向量" in result.keywords
        assert "数据" in result.keywords
        assert "检索" in result.keywords

    def test_chinese_single_char_no_bigram(self) -> None:
        """单字中文不产生 bigram"""
        processor = _make_processor()
        result = processor.process("你")
        # 单字不满足 bigram 条件（len < 2）
        assert len(result.keywords) == 0

    def test_chinese_two_chars_produces_one_bigram(self) -> None:
        """两字中文产生一个 bigram"""
        processor = _make_processor()
        result = processor.process("向量")
        assert result.keywords == ["向量"]

    def test_chinese_long_text_produces_multiple_bigrams(self) -> None:
        """长中文文本产生多个 bigram"""
        processor = _make_processor()
        result = processor.process("机器学习模型训练")
        # "机器学习模型训练" → bigrams: "机器", "器学", "学习", "习模", "模型", "型训", "训练"
        assert "机器" in result.keywords
        assert "学习" in result.keywords
        assert "模型" in result.keywords
        assert "训练" in result.keywords
        assert len(result.keywords) >= 6


# ============================================================
# TestMixedTextKeywordExtraction — 混合文本关键词提取
# ============================================================

class TestMixedTextKeywordExtraction:
    """中英混合文本关键词提取测试（3 个测试）

    知识点：混合文本分词策略
      - 英文词 + 中文 bigram 合并到同一列表
      - 英文词小写化去停用词，中文 bigram 去重
    """

    def test_mixed_chinese_english_query(self) -> None:
        """中英混合查询同时提取英文词和中文 bigram"""
        processor = _make_processor()
        result = processor.process("RAG 向量检索 system")
        assert "rag" in result.keywords
        assert "向量" in result.keywords
        assert "检索" in result.keywords
        assert "system" in result.keywords

    def test_mixed_with_stopwords(self) -> None:
        """混合文本中的英文停用词被过滤"""
        processor = _make_processor()
        result = processor.process("what is 向量检索")
        # "what" 和 "is" 是停用词
        assert "what" not in result.keywords
        assert "not" not in result.keywords
        assert "向量" in result.keywords
        assert "检索" in result.keywords

    def test_mixed_preserves_order(self) -> None:
        """混合文本关键词顺序：先英文后中文（按正则匹配顺序）"""
        processor = _make_processor()
        result = processor.process("embedding 向量")
        # 英文词先匹配
        assert result.keywords[0] == "embedding"
        assert "向量" in result.keywords


# ============================================================
# TestStopWordFiltering — 停用词过滤
# ============================================================

class TestStopWordFiltering:
    """停用词过滤测试（3 个测试）

    知识点：停用词策略
      - 与 SparseEncoder._EN_STOP_WORDS 对齐
      - 过滤无意义的常见词（the/a/is/...）
      - 面试考点："为什么要去停用词？" → 减少噪声，提升关键词质量
    """

    def test_common_stop_words_filtered(self) -> None:
        """常见停用词被过滤"""
        processor = _make_processor()
        result = processor.process("the quick brown fox jumps over the lazy dog")
        # "the" 是停用词
        assert "the" not in result.keywords
        # "over" 不在停用词表中，应保留
        assert "over" in result.keywords
        assert "quick" in result.keywords
        assert "brown" in result.keywords
        assert "fox" in result.keywords
        assert "jumps" in result.keywords
        assert "lazy" in result.keywords

    def test_all_stop_words_produce_empty_keywords(self) -> None:
        """全停用词查询产生空关键词列表"""
        processor = _make_processor()
        result = processor.process("the is a an of to in for")
        # 所有词都是停用词或 < 3 字母
        assert len(result.keywords) == 0

    def test_stop_words_case_insensitive(self) -> None:
        """停用词过滤不区分大小写"""
        processor = _make_processor()
        result = processor.process("The Quick Brown Fox")
        assert "the" not in result.keywords
        assert "quick" in result.keywords
        assert "brown" in result.keywords
        assert "fox" in result.keywords


# ============================================================
# TestDeduplication — 关键词去重
# ============================================================

class TestDeduplication:
    """关键词去重测试（2 个测试）

    知识点：查询端去重 vs 文档端不去重
      - QueryProcessor：关键词去重（检索只需要知道词项，不需要词频）
      - SparseEncoder：tokens 不去重（BM25 需要词频统计）
      - 面试考点："为什么查询端去重？" → 避免重复查询同一词项
    """

    def test_english_deduplication(self) -> None:
        """英文重复词只保留首次出现"""
        processor = _make_processor()
        result = processor.process("python python python")
        assert result.keywords.count("python") == 1

    def test_chinese_deduplication(self) -> None:
        """中文重复 bigram 只保留首次出现"""
        processor = _make_processor()
        result = processor.process("向量检索向量检索")
        assert result.keywords.count("向量") == 1
        assert result.keywords.count("检索") == 1


# ============================================================
# TestFiltersParsing — filters 解析
# ============================================================

class TestFiltersParsing:
    """filters 解析测试（4 个测试）

    知识点：filters 设计
      - None → {}（空过滤条件，不过滤）
      - dict → 原样返回（浅拷贝避免外部修改）
      - 非 dict 类型 → 容错降级为 {}
      - 面试考点："filters 是什么？" → metadata 过滤条件
    """

    def test_none_filters_returns_empty_dict(self) -> None:
        """None filters 返回空 dict"""
        processor = _make_processor()
        result = processor.process("test query", filters=None)
        assert isinstance(result.filters, dict)
        assert result.filters == {}

    def test_dict_filters_passed_through(self) -> None:
        """dict filters 原样透传"""
        processor = _make_processor()
        filters = {"doc_type": "pdf", "collection": "default"}
        result = processor.process("test query", filters=filters)
        assert result.filters == {"doc_type": "pdf", "collection": "default"}

    def test_filters_shallow_copy(self) -> None:
        """filters 是浅拷贝，外部修改不影响 ProcessedQuery"""
        processor = _make_processor()
        filters = {"doc_type": "pdf"}
        result = processor.process("test query", filters=filters)
        # 外部修改
        filters["doc_type"] = "md"
        # ProcessedQuery 中的 filters 不受影响
        assert result.filters["doc_type"] == "pdf"

    def test_non_dict_filters_degraded_to_empty(self) -> None:
        """非 dict 类型 filters 容错降级为空 dict"""
        processor = _make_processor()
        # list 类型
        result = processor.process("test query", filters=["a", "b"])  # type: ignore[arg-type]
        assert result.filters == {}

        # str 类型
        result = processor.process("test query", filters="doc_type:pdf")  # type: ignore[arg-type]
        assert result.filters == {}


# ============================================================
# TestExceptionHandling — 异常处理
# ============================================================

class TestExceptionHandling:
    """异常处理测试（2 个测试）

    知识点：QueryProcessor 是检索链路入口，Fail-Fast
      - 空查询直接抛 ValueError
      - 非字符串类型也抛 ValueError
      - 面试考点："为什么不降级而抛异常？" → 入口必须保证数据有效性
    """

    def test_empty_query_raises_value_error(self) -> None:
        """空查询抛 ValueError"""
        processor = _make_processor()
        with pytest.raises(ValueError, match="查询不能为空"):
            processor.process("")

    def test_whitespace_only_query_raises_value_error(self) -> None:
        """纯空白查询抛 ValueError"""
        processor = _make_processor()
        with pytest.raises(ValueError, match="查询不能为空"):
            processor.process("   \n\t  ")


# ============================================================
# TestTraceIntegration — Trace 集成
# ============================================================

class TestTraceIntegration:
    """Trace 集成测试（1 个测试，参数化 2 用例）

    知识点：TraceContext 的使用
      - process() 可选接受 trace 参数
      - trace 不为 None 时记录 query_processor 阶段
      - 记录内容：raw_query, keywords_count, keywords(截断), filters keys
    """

    @pytest.mark.parametrize("query,expected_kw_count", [
        ("python machine learning", 3),
        ("向量检索系统", 5),  # "向量","量检","检索","索系","系统"
    ])
    def test_trace_recorded_when_provided(
        self, query: str, expected_kw_count: int
    ) -> None:
        """提供 trace 时记录 query_processor 阶段"""
        processor = _make_processor()
        trace = TraceContext()

        processor.process(query, trace=trace)

        stages = trace.get_stages("query_processor")
        assert len(stages) == 1
        stage = stages[0]
        assert stage.data["raw_query"] == query
        assert stage.data["keywords_count"] == expected_kw_count
        assert len(stage.data["keywords"]) <= 20  # 截断
        assert stage.duration_ms is not None
        assert stage.duration_ms >= 0

    def test_no_trace_no_error(self) -> None:
        """不提供 trace 时不报错"""
        processor = _make_processor()
        # trace=None 应正常工作
        result = processor.process("test query", trace=None)
        assert result.keywords == ["test", "query"]

