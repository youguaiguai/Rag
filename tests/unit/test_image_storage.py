"""
ImageStorage 单元测试 — C13: 图片文件存储与索引映射

测试策略：
  - 使用 tmp_path 隔离文件系统
  - 验收标准全覆盖：
    1. 保存后文件存在
    2. 查找 image_id 返回正确路径
    3. 映射关系持久化在 SQLite
    4. 支持按 collection 批量查询
    5. 支持删除

测试分类（14 个）：
  - 保存 + 文件存在（3）
  - 查询路径（2）
  - 按 collection 查询（2）
  - 按 doc_hash 查询（2）
  - 删除（2）
  - 持久化 + 统计（3）
"""

from __future__ import annotations

import pytest
from ingestion.storage.image_storage import ImageStorage, ImageStorageError
from pathlib import Path


# ============================================================
# 辅助函数
# ============================================================

def _make_storage(tmp_path: Path) -> ImageStorage:
    """创建测试用 ImageStorage"""
    return ImageStorage(
        images_dir=str(tmp_path / "images"),
        db_path=str(tmp_path / "db" / "image_index.db"),
    )


# ============================================================
# 保存 + 文件存在（3 个）
# ============================================================

class TestSave:

    def test_save_creates_file(self, tmp_path):
        """验收标准：保存后文件存在"""
        storage = _make_storage(tmp_path)
        image_data = b"fake_png_data_12345"

        path = storage.save("img_001", image_data, collection="doc1")

        assert Path(path).exists()
        assert Path(path).read_bytes() == image_data

    def test_save_returns_correct_path(self, tmp_path):
        """返回的路径包含 collection 和 image_id"""
        storage = _make_storage(tmp_path)
        path = storage.save("img_002", b"data", collection="my_doc")

        assert "my_doc" in path
        assert "img_002" in path

    def test_save_idempotent(self, tmp_path):
        """同一 image_id 重复保存 → 覆盖（幂等）"""
        storage = _make_storage(tmp_path)
        storage.save("img_003", b"old_data", collection="doc1")
        storage.save("img_003", b"new_data", collection="doc1")

        path = storage.get_path("img_003")
        assert Path(path).read_bytes() == b"new_data"
        assert storage.count() == 1

    def test_save_different_extensions(self, tmp_path):
        """不同扩展名"""
        storage = _make_storage(tmp_path)
        path = storage.save("img_004", b"data", collection="doc1", extension=".jpg")

        assert path.endswith(".jpg")


# ============================================================
# 查询路径（2 个）
# ============================================================

class TestGetPath:

    def test_get_path_existing(self, tmp_path):
        """存在的 image_id → 返回路径"""
        storage = _make_storage(tmp_path)
        storage.save("img_010", b"data", collection="doc1")

        path = storage.get_path("img_010")
        assert path is not None
        assert Path(path).exists()

    def test_get_path_nonexistent(self, tmp_path):
        """不存在的 image_id → 返回 None"""
        storage = _make_storage(tmp_path)
        assert storage.get_path("nonexistent") is None


# ============================================================
# 按 collection 查询（2 个）
# ============================================================

class TestGetByCollection:

    def test_get_by_collection(self, tmp_path):
        """按 collection 批量查询"""
        storage = _make_storage(tmp_path)
        storage.save("img_a1", b"data1", collection="doc_a")
        storage.save("img_a2", b"data2", collection="doc_a")
        storage.save("img_b1", b"data3", collection="doc_b")

        results = storage.get_by_collection("doc_a")
        assert len(results) == 2
        ids = {r["image_id"] for r in results}
        assert ids == {"img_a1", "img_a2"}

    def test_get_by_collection_empty(self, tmp_path):
        """空 collection → 空列表"""
        storage = _make_storage(tmp_path)
        results = storage.get_by_collection("nonexistent")
        assert results == []


# ============================================================
# 按 doc_hash 查询（2 个）
# ============================================================

class TestGetByDocHash:

    def test_get_by_doc_hash(self, tmp_path):
        """按 doc_hash 查询文档所有图片"""
        storage = _make_storage(tmp_path)
        storage.save("img_1", b"d1", collection="c1", doc_hash="hash_abc")
        storage.save("img_2", b"d2", collection="c1", doc_hash="hash_abc")
        storage.save("img_3", b"d3", collection="c2", doc_hash="hash_xyz")

        results = storage.get_by_doc_hash("hash_abc")
        assert len(results) == 2
        assert all(r["doc_hash"] == "hash_abc" for r in results)

    def test_get_by_doc_hash_empty(self, tmp_path):
        """不存在的 doc_hash → 空列表"""
        storage = _make_storage(tmp_path)
        assert storage.get_by_doc_hash("nonexistent") == []


# ============================================================
# 删除（2 个）
# ============================================================

class TestDelete:

    def test_delete_single(self, tmp_path):
        """删除单个图片（文件 + 索引）"""
        storage = _make_storage(tmp_path)
        storage.save("img_del", b"data", collection="doc1")
        path = storage.get_path("img_del")
        assert Path(path).exists()

        result = storage.delete("img_del")
        assert result is True
        assert not Path(path).exists()
        assert storage.get_path("img_del") is None

    def test_delete_nonexistent_returns_false(self, tmp_path):
        """删除不存在的 → False"""
        storage = _make_storage(tmp_path)
        assert storage.delete("nonexistent") is False

    def test_delete_by_doc_hash(self, tmp_path):
        """按 doc_hash 删除文档所有图片"""
        storage = _make_storage(tmp_path)
        storage.save("img_1", b"d1", collection="c1", doc_hash="hash_del")
        storage.save("img_2", b"d2", collection="c1", doc_hash="hash_del")
        storage.save("img_3", b"d3", collection="c2", doc_hash="hash_keep")

        count = storage.delete_by_doc_hash("hash_del")
        assert count == 2
        assert storage.get_path("img_1") is None
        assert storage.get_path("img_2") is None
        assert storage.get_path("img_3") is not None


# ============================================================
# 持久化 + 统计（3 个）
# ============================================================

class TestPersistenceAndStats:

    def test_persistence_across_instances(self, tmp_path):
        """验收标准：映射关系持久化在 SQLite"""
        images_dir = str(tmp_path / "images")
        db_path = str(tmp_path / "db" / "image_index.db")

        # 第一个实例保存
        storage1 = ImageStorage(images_dir=images_dir, db_path=db_path)
        storage1.save("img_persist", b"data", collection="doc1")

        # 第二个实例查询（同一 db 文件）
        storage2 = ImageStorage(images_dir=images_dir, db_path=db_path)
        path = storage2.get_path("img_persist")

        assert path is not None
        assert Path(path).exists()

    def test_count(self, tmp_path):
        """统计图片总数"""
        storage = _make_storage(tmp_path)
        assert storage.count() == 0

        storage.save("img_1", b"d1", collection="c1")
        storage.save("img_2", b"d2", collection="c2")
        assert storage.count() == 2

    def test_count_by_collection(self, tmp_path):
        """按 collection 统计"""
        storage = _make_storage(tmp_path)
        storage.save("img_1", b"d1", collection="doc_a")
        storage.save("img_2", b"d2", collection="doc_a")
        storage.save("img_3", b"d3", collection="doc_b")

        assert storage.count_by_collection("doc_a") == 2
        assert storage.count_by_collection("doc_b") == 1
        assert storage.count_by_collection("nonexistent") == 0

