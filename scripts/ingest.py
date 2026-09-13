#!/usr/bin/env python3
"""
数据摄取脚本 — 离线 CLI 入口

知识点：CLI 入口脚本的设计原则
  - argparse 解析命令行参数
  - 支持 --collection / --path / --force 等选项
  - 调用 Ingestion Pipeline 完成摄取
  - 离线可用：不依赖 MCP Server，直接读写文件系统

使用方式：
  # 摄取单个文件
  python scripts/ingest.py --path /path/to/document.pdf

  # 摄取目录下所有文件
  python scripts/ingest.py --path /path/to/documents/

  # 强制重新摄取（跳过增量检查）
  python scripts/ingest.py --path /path/to/document.pdf --force

  # 指定 collection（用于按文档集分组）
  python scripts/ingest.py --path /path/to/document.pdf --collection my_project

  # 指定配置文件
  python scripts/ingest.py --path /path/to/document.pdf --config config/settings.yaml

面试考点：
  - "为什么需要 CLI 入口？" → 离线批量摄取，不需要启动服务
  - "argparse vs click？" → argparse 标准库无依赖，click 更优雅但需额外安装
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# 将 src/ 加入 sys.path（脚本独立运行时需要）
_src_dir = Path(__file__).parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from core.settings import load_settings  # noqa: E402
from ingestion.pipeline import IngestionPipeline, PipelineError  # noqa: E402

logger = logging.getLogger(__name__)


# ============================================================
# 支持的文件扩展名
# ============================================================

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".docx"}


def collect_files(path: str) -> list[str]:
    """收集要摄取的文件列表

    接口签名：collect_files(path: str) -> list[str]
    入参：path — 文件或目录路径
    出参：文件路径列表

    知识点：目录递归扫描
      - 如果 path 是文件 → 直接返回 [path]
      - 如果 path 是目录 → 递归扫描所有支持的文件
      - 面试考点："为什么过滤扩展名？" → 避免处理不支持的文件格式
    """
    p = Path(path)
    if p.is_file():
        return [str(p)]
    if p.is_dir():
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(str(f) for f in p.rglob(f"*{ext}"))
        return sorted(files)
    raise FileNotFoundError(f"路径不存在: {path}")


def run_ingest(
    file_paths: list[str],
    force: bool,
    config_path: str,
    collection: str | None = None,
) -> tuple[int, int, int]:
    """执行摄取流程

    接口签名：run_ingest(file_paths, force, config_path, collection) -> (success, skipped, failed)
    出参：(成功数, 跳过数, 失败数)
    """
    # 加载配置
    settings = load_settings(config_path)

    # 创建 Pipeline
    pipeline = IngestionPipeline(settings)

    # 注册进度回调（打印到控制台）
    def on_progress(stage: str, data: dict) -> None:
        if stage.endswith("_done") or stage in ("integrity_check",):
            logger.info("  [%s] %s", stage, data)

    pipeline.on_progress(on_progress)

    # 批量摄取
    results = pipeline.ingest_batch(file_paths, force=force)

    # 打印结果
    success_count = 0
    skipped_count = 0
    failed_count = 0

    print("\n" + "=" * 60)
    print("摄取结果汇总")
    print("=" * 60)

    for r in results:
        status_icon = {"success": "✅", "skipped": "⏭️", "failed": "❌"}.get(r.status, "?")
        print(f"  {status_icon} {r.file_path}")
        print(f"     状态: {r.status}", end="")
        if r.status == "success":
            print(f" | chunks={r.chunks} | dense={r.dense_records} | sparse={r.sparse_vectors} | {r.duration_ms:.0f}ms")
            success_count += 1
        elif r.status == "skipped":
            print(f" | {r.duration_ms:.0f}ms")
            skipped_count += 1
        else:
            print(f" | 错误: {r.error}")
            failed_count += 1

    print("=" * 60)
    print(f"  总计: {len(results)} 文件 | ✅ {success_count} 成功 | ⏭️ {skipped_count} 跳过 | ❌ {failed_count} 失败")
    print()

    return (success_count, skipped_count, failed_count)


def main() -> None:
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        description="RAG 数据摄取脚本 — 离线摄取文档到向量数据库和 BM25 索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --path document.pdf
  %(prog)s --path ./documents/ --force
  %(prog)s --path document.pdf --collection my_project
        """,
    )

    parser.add_argument(
        "--path", "-p",
        required=True,
        help="要摄取的文件或目录路径",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        default=False,
        help="强制重新摄取（跳过增量检查）",
    )
    parser.add_argument(
        "--collection", "-c",
        default=None,
        help="文档集合名称（用于按项目分组）",
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="配置文件路径（默认: config/settings.yaml）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="详细日志输出",
    )

    args = parser.parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 收集文件
    try:
        file_paths = collect_files(args.path)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    if not file_paths:
        print(f"未找到支持的文件: {args.path}")
        print(f"支持的格式: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        sys.exit(0)

    logger.info("找到 %d 个文件待摄取", len(file_paths))

    # 执行摄取
    start_time = time.monotonic()
    try:
        success_count, skipped_count, failed_count = run_ingest(
            file_paths=file_paths,
            force=args.force,
            config_path=args.config,
            collection=args.collection,
        )
    except PipelineError as e:
        print(f"摄取失败: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.monotonic() - start_time
    logger.info("总耗时: %.1fs", elapsed)

    # 只有全部失败才返回错误码（跳过不算失败）
    if failed_count > 0 and success_count == 0 and skipped_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

