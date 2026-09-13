"""
SparseEncoder 单元测试 — C9: BM25 统计与输出契约

测试策略：
  - 纯本地计算，无外部依赖
  - 验收标准全覆盖：
    1. 输出结构可用于 bm25_indexer（SparseVector 含 chunk_id/doc_id/terms/doc_len）
    2. 对空文本有明确行为（terms={}, doc_len=0）
    3. 词频统计正确
    4. 中文 bigram 分词正确
    5. 英文分词 + 停用词过滤

测试分类（18 个）：
  - 基础 + 空输入（3）
  - 分词正确性（4）
  - 词频统计（3）
  - 空文本处理（2）
  - 语料库统计（3）
  - BM25 分数计算（2）
  - Trace（1）
"""

from __future__ import annotations

import pytest
from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.embedding.sparse_encoder import (
    SparseEncoder,
    SparseVector,
    _tokenize,
)
from typing import Any


# ============================================================
# 辅助函数
# ============================================================

def _make_chunk(text: str, chunk_id: str = "c_0001", index: int = 0) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc123",
        text=text,
        index=index,
        source_ref=f"/test.md#chunk={index}",
        metadata={},
    )


# ============================================================
# 基础 + 空输入（3 个）
# ============================================================

class TestBasicAndEmpty:

    def test_empty_list_returns_empty(self):
        """空列表 → 空列表"""
        encoder = SparseEncoder(Settings())
        result = encoder.encode([])
        assert result == []

    def test_single_chunk(self):
        """单个 chunk → 单个 SparseVector"""
        encoder = SparseEncoder(Settings())
        chunk = _make_chunk("向量数据库检索")
        result = encoder.encode([chunk])

        assert len(result) == 1
        assert isinstance(result[0], SparseVector)

    def test_output_count_matches_input(self):
        """输出数量与输入一致"""
        encoder = SparseEncoder(Settings())
        chunks = [_make_chunk(f"文本{i}", chunk_id=f"c_{i}", index=i) for i in range(5)]
        result = encoder.encode(chunks)
        assert len(result) == 5


# ============================================================
# 分词正确性（4 个）
# ============================================================

class TestTokenization:

    def test_english_tokenization(self):
        """英文分词：3+ 字母词，小写化"""
        tokens = _tokenize("The Quick Brown Fox Jumps")
        assert "quick" in tokens
        assert "brown" in tokens
        assert "jumps" in tokens
        # 停用词过滤
        assert "the" not in tokens

    def test_short_english_words_filtered(self):
        """2 字母英文词被过滤"""
        tokens = _tokenize("go to no")
        assert len(tokens) == 0  # 全部 < 3 字母

    def test_chinese_bigram(self):
        """中文 bigram 分词"""
        tokens = _tokenize("向量数据库")
        # "向量", "量数", "数据", "据库"
        assert "向量" in tokens
        assert "数据" in tokens

    def test_mixed_text(self):
        """中英文混合分词"""
        tokens = _tokenize("RAG 系统使用 vector retrieval")
        assert "rag" in tokens
        assert "vector" in tokens
        assert "retrieval" in tokens
        assert "系统" in tokens


# ============================================================
# 词频统计（3 个）
# ============================================================

class TestTermFrequency:

    def test_tf_counts_correct(self):
        """词频统计正确"""
        encoder = SparseEncoder(Settings())
        chunk = _make_chunk("database database database query query")
        result = encoder.encode([chunk])

        terms = result[0].terms
        assert terms["database"] == 3
        assert terms["query"] == 2

    def test_doc_len_is_token_count(self):
        """doc_len = token 数量"""
        encoder = SparseEncoder(Settings())
        chunk = _make_chunk("database query search")
        result = encoder.encode([chunk])

        assert result[0].doc_len == 3

    def test_terms_dict_structure(self):
        """terms 是 dict[str, float]"""
        encoder = SparseEncoder(Settings())
        chunk = _make_chunk("hello world hello")
        result = encoder.encode([chunk])

        terms = result[0].terms
        assert isinstance(terms, dict)
        for v in terms.values():
            assert isinstance(v, (int, float))
            assert v > 0


# ============================================================
# 空文本处理（2 个）
# ============================================================

class TestEmptyText:

    def test_empty_text_produces_empty_terms(self):
        """空文本 → terms={}, doc_len=0"""
        encoder = SparseEncoder(Settings())
        chunk = _make_chunk("")
        result = encoder.encode([chunk])

        assert result[0].terms == {}
        assert result[0].doc_len == 0

    def test_whitespace_only_text(self):
        """纯空白文本 → terms={}, doc_len=0"""
        encoder = SparseEncoder(Settings())
        chunk = _make_chunk("   \n\t  ")
        result = encoder.encode([chunk])

        assert result[0].terms == {}
        assert result[0].doc_len == 0


# ============================================================
# 语料库统计（3 个）
# ============================================================

class TestCorpusStats:

    def test_compute_corpus_stats_basic(self):
        """语料库统计：N、avgdl、df、idf"""
        encoder = SparseEncoder(Settings())
        chunks = [
            _make_chunk("database query", chunk_id="c_0", index=0),
            _make_chunk("database search", chunk_id="c_1", index=1),
            _make_chunk("query optimization", chunk_id="c_2", index=2),
        ]
        vectors = encoder.encode(chunks)
        stats = SparseEncoder.compute_corpus_stats(vectors)

        assert stats["N"] == 3
        assert stats["avgdl"] > 0
        assert "df" in stats
        assert "idf" in stats

    def test_df_counts_documents_containing_term(self):
        """DF 统计：包含 term 的文档数"""
        encoder = SparseEncoder(Settings())
        chunks = [
            _make_chunk("database query", chunk_id="c_0", index=0),
            _make_chunk("database search", chunk_id="c_1", index=1),
            _make_chunk("query optimization", chunk_id="c_2", index=2),
        ]
        vectors = encoder.encode(chunks)
        stats = SparseEncoder.compute_corpus_stats(vectors)

        df = stats["df"]
        # "database" 出现在 2 个文档
        assert df["database"] == 2
        # "query" 出现在 2 个文档
        assert df["query"] == 2

    def test_idf_rarer_term_has_higher_value(self):
        """IDF：更稀有的 term IDF 更大"""
        encoder = SparseEncoder(Settings())
        chunks = [
            _make_chunk("common common common", chunk_id="c_0", index=0),
            _make_chunk("common rare", chunk_id="c_1", index=1),
        ]
        vectors = encoder.encode(chunks)
        stats = SparseEncoder.compute_corpus_stats(vectors)

        idf = stats["idf"]
        # "rare" 只在 1 个文档中，"common" 在 2 个文档中
        # IDF(rare) > IDF(common)（rare 更稀有）
        assert idf["rare"] > idf["common"]


# ============================================================
# BM25 分数计算（2 个）
# ============================================================

class TestBM25Score:

    def test_matching_term_produces_positive_score(self):
        """匹配的 term 产生正分"""
        encoder = SparseEncoder(Settings())
        chunks = [
            _make_chunk("vector database search", chunk_id="c_0", index=0),
            _make_chunk("image processing model", chunk_id="c_1", index=1),
        ]
        vectors = encoder.encode(chunks)
        stats = SparseEncoder.compute_corpus_stats(vectors)

        # 查询 "database" → 匹配 c_0
        query_terms = {"database": 1}
        score_0 = SparseEncoder.compute_bm25_score(query_terms, vectors[0], stats)
        score_1 = SparseEncoder.compute_bm25_score(query_terms, vectors[1], stats)

        assert score_0 > 0  # c_0 匹配
        assert score_1 == 0  # c_1 不匹配

    def test_non_matching_term_produces_zero_score(self):
        """不匹配的 term 分数为 0"""
        encoder = SparseEncoder(Settings())
        chunks = [_make_chunk("database query", chunk_id="c_0", index=0)]
        vectors = encoder.encode(chunks)
        stats = SparseEncoder.compute_corpus_stats(vectors)

        query_terms = {"nonexistent": 1}
        score = SparseEncoder.compute_bm25_score(query_terms, vectors[0], stats)
        assert score == 0


# ============================================================
# Trace（1 个）
# ============================================================

class TestTrace:

    def test_trace_records_stage(self):
        """trace 上下文记录阶段数据"""
        encoder = SparseEncoder(Settings())
        trace = TraceContext(trace_id="test-sparse")

        chunks = [
            _make_chunk("vector database retrieval", chunk_id="c_0", index=0),
            _make_chunk("machine learning model", chunk_id="c_1", index=1),
        ]
        encoder.encode(chunks, trace=trace)

        stages = trace.get_stages("sparse_encoder")
        assert len(stages) == 1
        assert stages[0].data["total"] == 2
        assert stages[0].data["total_tokens"] > 0
        assert stages[0].data["avg_doc_len"] > 0
        assert stages[0].data["unique_terms"] > 0

