"""C2: FileIntegrityChecker 单元测试

测试结构：
  1. 基本属性测试（3 个）
  2. compute_hash 测试（4 个）
  3. has_changed 测试（4 个）
  4. update_hash + get_hash 测试（3 个）
  5. save + load 持久化测试（4 个）
  6. remove + clear 测试（3 个）
  7. 增量摄取场景模拟（3 个）
"""

from __future__ import annotations

import json
import pytest
import tempfile
from libs.loader.file_integrity import FileIntegrityChecker, FileIntegrityError
from pathlib import Path


@pytest.fixture
def checker():
    """创建临时 FileIntegrityChecker 实例"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        db_path = f.name
    c = FileIntegrityChecker(db_path=db_path)
    yield c
    # 清理临时文件
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_file():
    """创建临时文件"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"test content for hashing")
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


class TestBasicProperties:

    def test_db_path(self, checker):
        """db_path 属性正确"""
        assert isinstance(checker.db_path, str)
        assert checker.db_path.endswith(".json")

    def test_count_initial(self, checker):
        """初始 count 为 0"""
        assert checker.count == 0

    def test_get_all_paths_initial(self, checker):
        """初始 get_all_paths 为空"""
        assert checker.get_all_paths() == []


class TestComputeHash:

    def test_returns_string(self, checker, temp_file):
        """返回字符串"""
        h = checker.compute_hash(temp_file)
        assert isinstance(h, str)

    def test_hash_length(self, checker, temp_file):
        """SHA256 哈希长度为 64 字符"""
        h = checker.compute_hash(temp_file)
        assert len(h) == 64

    def test_deterministic(self, checker, temp_file):
        """相同文件 → 相同哈希"""
        h1 = checker.compute_hash(temp_file)
        h2 = checker.compute_hash(temp_file)
        assert h1 == h2

    def test_file_not_found(self, checker):
        """文件不存在 → FileIntegrityError"""
        with pytest.raises(FileIntegrityError, match="文件不存在"):
            checker.compute_hash("/nonexistent/file.pdf")


class TestHasChanged:

    def test_new_file_changed(self, checker, temp_file):
        """首次出现的文件 → True（需要处理）"""
        assert checker.has_changed(temp_file) is True

    def test_unchanged_file(self, checker, temp_file):
        """未变更的文件 → False（跳过）"""
        checker.update_hash(temp_file)
        assert checker.has_changed(temp_file) is False

    def test_changed_file(self, checker, temp_file):
        """内容变更的文件 → True"""
        checker.update_hash(temp_file)
        # 修改文件内容
        with open(temp_file, "wb") as f:
            f.write(b"modified content")
        assert checker.has_changed(temp_file) is True

    def test_different_files_different_hashes(self, checker):
        """不同文件 → 不同哈希"""
        with tempfile.NamedTemporaryFile(delete=False) as f1, \
             tempfile.NamedTemporaryFile(delete=False) as f2:
            f1.write(b"content A")
            f2.write(b"content B")
            p1, p2 = f1.name, f2.name
        try:
            h1 = checker.compute_hash(p1)
            h2 = checker.compute_hash(p2)
            assert h1 != h2
        finally:
            Path(p1).unlink(missing_ok=True)
            Path(p2).unlink(missing_ok=True)


class TestUpdateAndGetHash:

    def test_update_returns_hash(self, checker, temp_file):
        """update_hash 返回当前哈希"""
        h = checker.update_hash(temp_file)
        assert len(h) == 64

    def test_get_hash_after_update(self, checker, temp_file):
        """update 后 get_hash 返回存储的哈希"""
        h = checker.update_hash(temp_file)
        assert checker.get_hash(temp_file) == h

    def test_get_hash_not_recorded(self, checker):
        """未记录的文件 → None"""
        assert checker.get_hash("/nonexistent.pdf") is None


class TestSaveLoad:

    def test_save_creates_file(self, checker, temp_file):
        """save 创建 JSON 文件"""
        checker.update_hash(temp_file)
        checker.save()
        assert Path(checker.db_path).exists()

    def test_load_restores_hashes(self, checker, temp_file):
        """save → load 恢复哈希记录"""
        checker.update_hash(temp_file)
        checker.save()

        # 创建新的 checker 加载同一 db
        c2 = FileIntegrityChecker(db_path=checker.db_path)
        assert c2.get_hash(temp_file) is not None
        assert c2.get_hash(temp_file) == checker.get_hash(temp_file)

    def test_load_nonexistent_file(self):
        """load 不存在的文件 → 空字典"""
        c = FileIntegrityChecker(db_path="/nonexistent/path/hashes.json")
        assert c.count == 0
        assert c.get_all_paths() == []

    def test_load_corrupted_json(self):
        """load 损坏的 JSON → 空字典（容错）"""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("{ broken json")
            db_path = f.name
        try:
            c = FileIntegrityChecker(db_path=db_path)
            assert c.count == 0
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestRemoveAndClear:

    def test_remove_existing(self, checker, temp_file):
        """删除存在的记录 → True"""
        checker.update_hash(temp_file)
        assert checker.remove(temp_file) is True
        assert checker.get_hash(temp_file) is None

    def test_remove_nonexistent(self, checker):
        """删除不存在的记录 → False"""
        assert checker.remove("/nonexistent.pdf") is False

    def test_clear(self, checker, temp_file):
        """clear 清空所有记录"""
        checker.update_hash(temp_file)
        assert checker.count > 0
        checker.clear()
        assert checker.count == 0
        assert checker.get_all_paths() == []


class TestIncrementalIngestionScenario:
    """模拟增量摄取的完整场景"""

    def test_first_run_processes_all(self, checker):
        """首次运行：所有文件都是新的"""
        files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(f"content {i}".encode())
                files.append(f.name)

        try:
            # 首次运行：所有文件都应被处理
            changed = [f for f in files if checker.has_changed(f)]
            assert len(changed) == 3

            # 处理后更新哈希
            for f in files:
                checker.update_hash(f)
        finally:
            for f in files:
                Path(f).unlink(missing_ok=True)

    def test_second_run_skips_unchanged(self, checker):
        """第二次运行：跳过未变更文件"""
        files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(f"content {i}".encode())
                files.append(f.name)

        try:
            # 首次运行：全部处理 + 更新哈希
            for f in files:
                checker.update_hash(f)

            # 第二次运行：全部跳过
            changed = [f for f in files if checker.has_changed(f)]
            assert len(changed) == 0
        finally:
            for f in files:
                Path(f).unlink(missing_ok=True)

    def test_modified_file_detected(self, checker):
        """修改文件后检测到变更"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"original content")
            path = f.name

        try:
            # 首次处理
            checker.update_hash(path)
            assert checker.has_changed(path) is False

            # 修改文件
            with open(path, "wb") as f:
                f.write(b"modified content")

            # 检测到变更
            assert checker.has_changed(path) is True

            # 重新处理 + 更新哈希
            checker.update_hash(path)
            assert checker.has_changed(path) is False
        finally:
            Path(path).unlink(missing_ok=True)

