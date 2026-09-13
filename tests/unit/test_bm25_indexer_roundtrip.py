"""
BM25Indexer 单元测试 — C11: 倒排索引构建与持久化

测试策略：
  - 使用 tmp_path 隔离文件系统
  - 验收标准全覆盖：
    1. build 后能 load 并对同一语料查询返回稳定 top ids
    2. IDF 计算准确（可用已知语料对比验证）
    3. 支持索引重建与增量更新

测试分类（16 个）：
  - 构建基础（3）
  - IDF 计算准确性（2）
  - 查询（3）
  - 持久化 round-trip（3）
  - 重建（1）
  - 增量更新（2）
  - 边界 + 属性（2）
"""

from __future__ import annotations

import json
import math
import pytest
from ingestion.embedding.sparse_encoder import SparseVector
from ingestion.storage.bm25_indexer import BM25Indexer
from pathlib import Path


# ============================================================
# 辅助函数
# ============================================================

def _make_vec(chunk_id: str, terms: dict[str, float], doc_len: int = 0,
              doc_id: str = "doc1") -> SparseVector:
    """创建 SparseVector"""
    if doc_len == 0:
        doc_len = int(sum(terms.values())) if terms else 0
    return SparseVector(
        chunk_id=chunk_id,
        doc_id=doc_id,
        terms=terms,
        doc_len=doc_len,
    )


def _make_corpus() -> list[SparseVector]:
    """创建已知语料库（用于 IDF 验证）

    语料库设计：
      - c0: "database query search" → {database:1, query:1, search:1}, len=3
      - c1: "database index search" → {database:1, index:1, search:1}, len=3
      - c2: "query optimization" → {query:1, optimization:1}, len=2

    DF 统计：
      - database: 2 (c0, c1)
      - query: 2 (c0, c2)
      - search: 2 (c0, c1)
      - index: 1 (c1)
      - optimization: 1 (c2)

    N = 3
    """
    return [
        _make_vec("c0", {"database": 1, "query": 1, "search": 1}, 3),
        _make_vec("c1", {"database": 1, "index": 1, "search": 1}, 3),
        _make_vec("c2", {"query": 1, "optimization": 1}, 2),
    ]


# ============================================================
# 构建基础（3 个）
# ============================================================

class TestBuild:

    def test_build_basic(self, tmp_path):
        """基本构建：3 文档 → 索引"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        vectors = _make_corpus()
        indexer.build(vectors)

        assert indexer.num_docs == 3
        assert indexer.num_terms == 5  # database, query, search, index, optimization
        assert indexer.avgdl > 0

    def test_build_empty(self, tmp_path):
        """空列表 → N=0, terms=0"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build([])

        assert indexer.num_docs == 0
        assert indexer.num_terms == 0
        # 索引文件应该被创建（空索引）
        assert indexer.index_path.exists()

    def test_build_persists_to_file(self, tmp_path):
        """build 后索引文件存在"""
        bm25_dir = tmp_path / "bm25"
        indexer = BM25Indexer(persist_path=str(bm25_dir))
        indexer.build(_make_corpus())

        assert bm25_dir.exists()
        assert (bm25_dir / "bm25_index.json").exists()


# ============================================================
# IDF 计算准确性（2 个）
# ============================================================

class TestIDFAccuracy:

    def test_idf_values_correct(self, tmp_path):
        """IDF 值与手动计算一致"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())

        # 直接检查索引中的 IDF 值
        index = indexer._index["index"]
        N = 3

        # database: df=2, N=3 → IDF = ln((3-2+0.5)/(2+0.5)+1) = ln(1.6) ≈ 0.470
        expected_db = math.log((N - 2 + 0.5) / (2 + 0.5) + 1)
        assert abs(index["database"]["idf"] - expected_db) < 1e-6

        # index: df=1, N=3 → IDF = ln((3-1+0.5)/(1+0.5)+1) = ln(2.667) ≈ 0.981
        expected_idx = math.log((N - 1 + 0.5) / (1 + 0.5) + 1)
        assert abs(index["index"]["idf"] - expected_idx) < 1e-6

    def test_rarer_term_has_higher_idf(self, tmp_path):
        """更稀有的 term IDF 更大"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())

        index = indexer._index["index"]
        # "index" (df=1) 比 "database" (df=2) 更稀有
        assert index["index"]["idf"] > index["database"]["idf"]


# ============================================================
# 查询（3 个）
# ============================================================

class TestSearch:

    def test_search_returns_matching_docs(self, tmp_path):
        """查询返回匹配的文档"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())

        # 查询 "database" → 匹配 c0, c1
        results = indexer.search({"database": 1})
        chunk_ids = [cid for cid, _ in results]

        assert "c0" in chunk_ids
        assert "c1" in chunk_ids
        assert "c2" not in chunk_ids

    def test_search_top_k_limit(self, tmp_path):
        """top_k 限制返回数量"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())

        results = indexer.search({"database": 1}, top_k=1)
        assert len(results) == 1

    def test_search_scores_descending(self, tmp_path):
        """结果按分数降序排列"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())

        results = indexer.search({"database": 1, "search": 1}, top_k=10)
        scores = [s for _, s in results]

        assert scores == sorted(scores, reverse=True)


# ============================================================
# 持久化 round-trip（3 个）
# ============================================================

class TestPersistenceRoundTrip:

    def test_build_then_load_then_search_stable(self, tmp_path):
        """验收标准：build → load → 查询返回稳定 top ids"""
        # Build
        indexer1 = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer1.build(_make_corpus())
        results1 = indexer1.search({"database": 1, "search": 1}, top_k=5)

        # Load
        indexer2 = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer2.load()
        results2 = indexer2.search({"database": 1, "search": 1}, top_k=5)

        # 结果一致
        assert results1 == results2

    def test_load_nonexistent_raises(self, tmp_path):
        """加载不存在的索引 → FileNotFoundError"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "nonexistent"))
        with pytest.raises(FileNotFoundError):
            indexer.load()

    def test_loaded_index_has_same_stats(self, tmp_path):
        """load 后统计数据一致"""
        indexer1 = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer1.build(_make_corpus())

        indexer2 = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer2.load()

        assert indexer2.num_docs == indexer1.num_docs
        assert indexer2.num_terms == indexer1.num_terms
        assert abs(indexer2.avgdl - indexer1.avgdl) < 1e-6


# ============================================================
# 重建（1 个）
# ============================================================

class TestRebuild:

    def test_rebuild_replaces_old_index(self, tmp_path):
        """rebuild 清空旧索引重建"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())
        assert indexer.num_docs == 3

        # 重建为不同语料
        new_corpus = [
            _make_vec("d0", {"python": 2, "code": 1}, 3),
            _make_vec("d1", {"java": 1, "code": 1}, 2),
        ]
        indexer.rebuild(new_corpus)

        assert indexer.num_docs == 2
        assert "python" in indexer._index["index"]
        assert "database" not in indexer._index["index"]


# ============================================================
# 增量更新（2 个）
# ============================================================

class TestUpsert:

    def test_upsert_adds_new_document(self, tmp_path):
        """upsert 新增文档"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())
        assert indexer.num_docs == 3

        # 新增 c3
        new_vec = _make_vec("c3", {"database": 2, "cache": 1}, 3)
        indexer.upsert([new_vec])

        assert indexer.num_docs == 4
        results = indexer.search({"cache": 1})
        chunk_ids = [cid for cid, _ in results]
        assert "c3" in chunk_ids

    def test_upsert_updates_existing_document(self, tmp_path):
        """upsert 更新已有文档"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())

        # 更新 c0（改变 terms）
        updated_vec = _make_vec("c0", {"python": 3, "code": 1}, 4)
        indexer.upsert([updated_vec])

        assert indexer.num_docs == 3  # 文档数不变

        # c0 应该不再匹配 "database"（旧 terms 已被替换）
        results = indexer.search({"database": 1})
        chunk_ids = [cid for cid, _ in results]
        assert "c0" not in chunk_ids

        # c0 应该匹配 "python"
        results = indexer.search({"python": 1})
        chunk_ids = [cid for cid, _ in results]
        assert "c0" in chunk_ids


# ============================================================
# 边界 + 属性（2 个）
# ============================================================

class TestEdgeAndProperties:

    def test_search_empty_index_returns_empty(self, tmp_path):
        """空索引查询 → 空列表"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build([])

        results = indexer.search({"anything": 1})
        assert results == []

    def test_search_no_matching_terms_returns_empty(self, tmp_path):
        """查询词不在索引中 → 空列表"""
        indexer = BM25Indexer(persist_path=str(tmp_path / "bm25"))
        indexer.build(_make_corpus())

        results = indexer.search({"nonexistent_term": 1})
        assert results == []

