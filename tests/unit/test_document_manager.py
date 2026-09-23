"""
DocumentManager 单元测试 — G2: 文档生命周期管理

测试策略：
  - Mock 各存储组件
  - 验证跨存储协调逻辑
  - 验证 list / detail / delete / stats
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# 确保 src/ 在路径中
_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from ingestion.document_manager import (
    DocumentManager,
    DocumentInfo,
    DocumentDetail,
    DeleteResult,
    CollectionStats,
)


# ============================================================
# 辅助函数
# ============================================================

def _make_mock_chroma(records: list[dict[str, Any]] | None = None) -> Any:
    """创建 Mock ChromaStore"""
    mock = MagicMock()
    mock.get_all_records.return_value = records or []
    mock.delete_by_metadata.return_value = 0
    return mock


def _make_mock_bm25() -> Any:
    """创建 Mock BM25Indexer"""
    mock = MagicMock()
    mock.remove_document.return_value = 0
    mock.list_all_chunk_ids.return_value = []
    return mock


def _make_mock_integrity() -> Any:
    """创建 Mock FileIntegrityChecker"""
    mock = MagicMock()
    mock.remove.return_value = True
    return mock


def _make_manager(
    chroma_records: list[dict[str, Any]] | None = None,
) -> DocumentManager:
    """创建 Mock DocumentManager"""
    chroma = _make_mock_chroma(chroma_records)
    bm25 = _make_mock_bm25()
    integrity = _make_mock_integrity()
    return DocumentManager(chroma, bm25, integrity)


# ============================================================
# TestListDocuments — 文档列表测试
# ============================================================

class TestListDocuments:
    """list_documents 测试（4 个测试）"""

    def test_empty_list(self) -> None:
        """无文档时返回空列表"""
        manager = _make_manager([])
        docs = manager.list_documents()
        assert docs == []

    def test_single_document(self) -> None:
        """单文档返回正确信息"""
        records = [
            {"id": "chunk1", "text": "text", "metadata": {"source": "doc1.md", "doc_id": "d1"}},
            {"id": "chunk2", "text": "text", "metadata": {"source": "doc1.md", "doc_id": "d1"}},
        ]
        manager = _make_manager(records)
        docs = manager.list_documents()

        assert len(docs) == 1
        assert docs[0].source_path == "doc1.md"
        assert docs[0].chunk_count == 2

    def test_multiple_documents(self) -> None:
        """多文档正确聚合"""
        records = [
            {"id": "c1", "text": "t", "metadata": {"source": "doc1.md"}},
            {"id": "c2", "text": "t", "metadata": {"source": "doc1.md"}},
            {"id": "c3", "text": "t", "metadata": {"source": "doc2.md"}},
        ]
        manager = _make_manager(records)
        docs = manager.list_documents()

        assert len(docs) == 2
        sources = {d.source_path for d in docs}
        assert sources == {"doc1.md", "doc2.md"}

    def test_chroma_failure_returns_empty(self) -> None:
        """Chroma 异常时返回空列表（不抛异常）"""
        chroma = MagicMock()
        chroma.get_all_records.side_effect = RuntimeError("DB Error")
        manager = DocumentManager(chroma, _make_mock_bm25(), _make_mock_integrity())

        docs = manager.list_documents()
        assert docs == []


# ============================================================
# TestDeleteDocument — 文档删除测试
# ============================================================

class TestDeleteDocument:
    """delete_document 测试（4 个测试）"""

    def test_delete_calls_all_stores(self) -> None:
        """删除操作调用所有存储"""
        manager = _make_manager()
        result = manager.delete_document("doc1.md")

        manager._chroma.delete_by_metadata.assert_called_once()
        manager._bm25.remove_document.assert_called_once_with("doc1.md")
        manager._integrity.remove.assert_called_once_with("doc1.md")

    def test_delete_returns_result(self) -> None:
        """删除返回 DeleteResult"""
        manager = _make_manager()
        result = manager.delete_document("test.md")

        assert isinstance(result, DeleteResult)
        assert result.source_path == "test.md"

    def test_delete_counts(self) -> None:
        """删除计数正确"""
        chroma = _make_mock_chroma()
        chroma.delete_by_metadata.return_value = 5
        bm25 = _make_mock_bm25()
        bm25.remove_document.return_value = 3
        manager = DocumentManager(chroma, bm25, _make_mock_integrity())

        result = manager.delete_document("doc.md")
        assert result.chroma_deleted == 5
        assert result.bm25_deleted == 3
        assert result.integrity_removed is True

    def test_delete_isolation(self) -> None:
        """单个存储失败不影响其他"""
        chroma = _make_mock_chroma()
        chroma.delete_by_metadata.side_effect = RuntimeError("Chroma error")
        manager = DocumentManager(chroma, _make_mock_bm25(), _make_mock_integrity())

        result = manager.delete_document("doc.md")
        # BM25 和 Integrity 仍然被调用
        manager._bm25.remove_document.assert_called_once()
        manager._integrity.remove.assert_called_once()


# ============================================================
# TestCollectionStats — 统计测试
# ============================================================

class TestCollectionStats:
    """get_collection_stats 测试（2 个测试）"""

    def test_stats_count(self) -> None:
        """统计数正确"""
        records = [
            {"id": "c1", "text": "t", "metadata": {"source": "a.md"}},
            {"id": "c2", "text": "t", "metadata": {"source": "a.md"}},
            {"id": "c3", "text": "t", "metadata": {"source": "b.md"}},
        ]
        manager = _make_manager(records)
        stats = manager.get_collection_stats()

        assert isinstance(stats, CollectionStats)
        assert stats.total_chunks == 3
        assert stats.total_documents == 2

    def test_empty_stats(self) -> None:
        """空库统计为 0"""
        manager = _make_manager([])
        stats = manager.get_collection_stats()
        assert stats.total_chunks == 0
        assert stats.total_documents == 0

