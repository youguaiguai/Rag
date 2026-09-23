"""
Pipeline 进度回调单元测试 — F5: on_progress 回调

测试策略：
  - Mock 回调函数验证被正确调用
  - 验证回调参数：(stage_name, current, total)
  - 验证 on_progress=None 时不影响行为

测试分类（6 个）：
  - 回调调用验证（4）
  - None 回调安全（1）
  - 回调异常隔离（1）
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 确保 src/ 在路径中
_src_dir = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


def _make_settings(tmp_path: Path):
    """创建测试用 Settings"""
    from core.settings import Settings
    s = Settings()
    if hasattr(s, "observability"):
        s.observability.db_path = str(tmp_path / "file_hashes.json")
    if hasattr(s, "vector_store"):
        s.vector_store.backend = "fake"
    # 关键：设置 embedding 为 fake 模式，避免真实 API 调用
    if hasattr(s, "embedding"):
        s.embedding.provider = "fake"
        s.embedding.model = "fake-model"
    if hasattr(s, "vision_llm"):
        s.vision_llm.provider = "fake"
        s.vision_llm.enabled = False  # 禁用避免真实调用
    if hasattr(s, "metadata_enricher"):
        s.metadata_enricher.enabled = False
    return s


def _make_markdown_file(tmp_path: Path) -> str:
    """创建测试用 Markdown 文件"""
    file_path = tmp_path / "test_doc.md"
    file_path.write_text("# Test Document\n\nThis is a test document for F5 progress callback.\n" * 50, encoding="utf-8")
    return str(file_path)


def _make_pipeline(tmp_path: Path):
    """创建测试用 Pipeline"""
    settings = _make_settings(tmp_path)
    from ingestion.pipeline import IngestionPipeline
    return IngestionPipeline(settings)


# ============================================================
# TestOnProgressCallback — 进度回调测试
# ============================================================

class TestOnProgressCallback:
    """on_progress 回调测试（6 个测试）"""

    def test_callback_called_for_each_stage(self, tmp_path: Path) -> None:
        """回调在每个阶段被调用"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)
        mock_callback = MagicMock()

        pipeline.ingest(file_path, force=True, on_progress=mock_callback)

        # 验证回调被调用（load, split, transform, embed, upsert = 5 个阶段）
        assert mock_callback.call_count == 5

    def test_callback_receives_correct_stage_names(self, tmp_path: Path) -> None:
        """回调接收正确的阶段名称"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)
        mock_callback = MagicMock()

        pipeline.ingest(file_path, force=True, on_progress=mock_callback)

        # 提取所有调用的 stage_name
        called_stages = [call.args[0] for call in mock_callback.call_args_list]
        assert called_stages == ["load", "split", "transform", "embed", "upsert"]

    def test_callback_receives_correct_progress(self, tmp_path: Path) -> None:
        """回调接收正确的 current/total"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)
        mock_callback = MagicMock()

        pipeline.ingest(file_path, force=True, on_progress=mock_callback)

        # 验证 total 始终为 5
        for call in mock_callback.call_args_list:
            _, current, total = call.args
            assert total == 5
            assert 1 <= current <= 5

    def test_callback_none_is_safe(self, tmp_path: Path) -> None:
        """on_progress=None 时不影响行为"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        # 不应抛异常，正常返回结果
        result = pipeline.ingest(file_path, force=True, on_progress=None)
        assert result.status == "success"

    def test_callback_exception_is_isolated(self, tmp_path: Path) -> None:
        """回调异常不影响 pipeline 执行"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)

        def bad_callback(stage: str, current: int, total: int) -> None:
            raise RuntimeError("Callback error!")

        # 即使回调抛异常，pipeline 仍应成功
        result = pipeline.ingest(file_path, force=True, on_progress=bad_callback)
        assert result.status == "success"

    def test_callback_called_in_order(self, tmp_path: Path) -> None:
        """回调按阶段顺序调用"""
        pipeline = _make_pipeline(tmp_path)
        file_path = _make_markdown_file(tmp_path)
        mock_callback = MagicMock()

        pipeline.ingest(file_path, force=True, on_progress=mock_callback)

        # 验证 current 递增
        currents = [call.args[1] for call in mock_callback.call_args_list]
        assert currents == [1, 2, 3, 4, 5]

