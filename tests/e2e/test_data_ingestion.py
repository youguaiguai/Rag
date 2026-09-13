"""
E2E 测试 — C15: 数据摄取脚本入口

测试策略：
  - 使用 subprocess 调用 scripts/ingest.py（真实 CLI 运行）
  - 使用 tmp_path 隔离文件系统和产物
  - 使用 fake provider 配置（不依赖真实 API）
  - 验收标准：命令行可运行并在 data/db 产生产物；重复运行在未变更时跳过

测试分类（7 个）：
  - 基础 CLI 运行（2）
  - 增量摄取（2）
  - force 强制重摄（1）
  - 目录摄取（1）
  - 错误处理（1）
"""

from __future__ import annotations

import pytest
import subprocess
import sys
import yaml
from pathlib import Path

# ============================================================
# 辅助函数
# ============================================================

SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "ingest.py"
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _make_config(tmp_path: Path) -> str:
    """创建测试用配置文件（使用 fake provider）"""
    config = {
        "llm": {
            "provider": "fake",
            "model": "fake-model",
            "api_key": "",
        },
        "embedding": {
            "provider": "fake",
            "model": "fake-embedding",
            "dimensions": 32,
        },
        "vision_llm": {
            "enabled": False,
            "provider": "fake",
            "model": "fake-vision",
            "api_key": "",
        },
        "splitter": {
            "provider": "recursive",
            "chunk_size": 200,
            "chunk_overlap": 50,
        },
        "ingestion": {
            "chunk_refiner": {
                "use_llm": False,
            },
            "metadata_enricher": {
                "use_llm": False,
                "max_tags": 5,
            },
            "image_captioner": {
                "prompt_path": "config/prompts/image_captioning.txt",
            },
        },
        "vector_store": {
            "backend": "fake",
            "persist_path": str(tmp_path / "chroma"),
        },
        "retrieval": {
            "sparse_backend": "bm25",
            "fusion_algorithm": "rrf",
            "top_k_dense": 20,
            "top_k_sparse": 20,
            "top_k_final": 10,
        },
        "rerank": {
            "enabled": False,
            "backend": "none",
            "top_m": 30,
        },
    }
    config_path = tmp_path / "settings.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)
    return str(config_path)


def _make_markdown(tmp_path: Path, name: str = "test.md", content: str = "") -> str:
    """创建测试用 Markdown 文件"""
    if not content:
        content = """# 测试文档

## 第一章

这是一个测试文档，用于验证 CLI 摄取功能。

## 第二章

包含多个段落和章节，确保能正确切分。
"""
    file_path = tmp_path / name
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def _run_ingest(args: list[str]) -> subprocess.CompletedProcess:
    """运行 ingest.py 脚本"""
    cmd = [sys.executable, str(SCRIPT_PATH)] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    return result


# ============================================================
# 基础 CLI 运行（2 个）
# ============================================================

class TestBasicCLI:

    def test_ingest_single_file_success(self, tmp_path):
        """验收标准：命令行可运行并产生产物"""
        config_path = _make_config(tmp_path)
        md_path = _make_markdown(tmp_path)

        result = _run_ingest([
            "--path", md_path,
            "--config", config_path,
        ])

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "✅" in result.stdout
        assert "成功" in result.stdout

    def test_ingest_output_shows_summary(self, tmp_path):
        """输出包含结果汇总"""
        config_path = _make_config(tmp_path)
        md_path = _make_markdown(tmp_path)

        result = _run_ingest([
            "--path", md_path,
            "--config", config_path,
        ])

        assert "摄取结果汇总" in result.stdout
        assert "总计" in result.stdout


# ============================================================
# 增量摄取（2 个）
# ============================================================

class TestIncrementalIngestion:

    def test_unchanged_file_skipped(self, tmp_path):
        """验收标准：重复运行在未变更时跳过"""
        config_path = _make_config(tmp_path)
        md_path = _make_markdown(tmp_path)

        # 第一次摄取
        result1 = _run_ingest(["--path", md_path, "--config", config_path])
        assert result1.returncode == 0
        assert "✅" in result1.stdout

        # 第二次摄取（未变更 → 跳过）
        result2 = _run_ingest(["--path", md_path, "--config", config_path])
        assert result2.returncode == 0
        # 汇总行应显示 1 跳过
        assert "1 跳过" in result2.stdout

    def test_modified_file_reingested(self, tmp_path):
        """文件变更后重新摄取"""
        config_path = _make_config(tmp_path)
        md_path = _make_markdown(tmp_path, content="# 原始内容\n\n段落1。")

        # 第一次摄取
        result1 = _run_ingest(["--path", md_path, "--config", config_path])
        assert "✅" in result1.stdout

        # 修改文件
        Path(md_path).write_text("# 修改后的内容\n\n段落2。更多内容。", encoding="utf-8")

        # 第二次摄取（文件变更 → 重新摄取）
        result2 = _run_ingest(["--path", md_path, "--config", config_path])
        assert "✅" in result2.stdout


# ============================================================
# force 强制重摄（1 个）
# ============================================================

class TestForceFlag:

    def test_force_reingests_unchanged(self, tmp_path):
        """--force 强制重新摄取未变更文件"""
        config_path = _make_config(tmp_path)
        md_path = _make_markdown(tmp_path)

        # 第一次摄取
        result1 = _run_ingest(["--path", md_path, "--config", config_path])
        assert "✅" in result1.stdout

        # 强制重新摄取
        result2 = _run_ingest(["--path", md_path, "--config", config_path, "--force"])
        assert result2.returncode == 0
        assert "✅" in result2.stdout
        assert "0 跳过" in result2.stdout  # force 时不应跳过


# ============================================================
# 目录摄取（1 个）
# ============================================================

class TestDirectoryIngestion:

    def test_ingest_directory_multiple_files(self, tmp_path):
        """摄取目录下多个文件"""
        config_path = _make_config(tmp_path)
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        _make_markdown(docs_dir, "doc1.md", "# 文档1\n\n内容1。")
        _make_markdown(docs_dir, "doc2.md", "# 文档2\n\n内容2。")

        result = _run_ingest(["--path", str(docs_dir), "--config", config_path])

        assert result.returncode == 0
        assert "2 文件" in result.stdout or "2 成功" in result.stdout


# ============================================================
# 错误处理（1 个）
# ============================================================

class TestErrorHandling:

    def test_nonexistent_path_exits_with_error(self, tmp_path):
        """不存在的路径 → 非零退出码"""
        config_path = _make_config(tmp_path)

        result = _run_ingest([
            "--path", "/nonexistent/path/to/file.md",
            "--config", config_path,
        ])

        assert result.returncode != 0
        assert "错误" in result.stderr or "错误" in result.stdout

