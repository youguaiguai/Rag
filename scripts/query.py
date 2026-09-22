#!/usr/bin/env python3
"""
查询脚本 — 在线 CLI 入口

知识点：CLI 查询工具的设计原则
  - argparse 解析命令行参数
  - 调用完整的 HybridSearch + Reranker 流程
  - 格式化输出检索结果
  - 开发调试用（生产环境通过 MCP Server 暴露查询接口）

使用方式：
  # 基础查询
  python scripts/query.py --query "如何配置 Azure？"

  # 指定返回数量
  python scripts/query.py --query "什么是 RAG？" --top-k 5

  # 限定集合
  python scripts/query.py --query "向量数据库" --collection default

  # Verbose 模式（显示各阶段中间结果）
  python scripts/query.py --query "BM25 算法" --verbose

  # 跳过 Reranker
  python scripts/query.py --query "测试" --no-rerank

  # 指定配置文件
  python scripts/query.py --query "测试" --config config/settings.yaml

面试考点：
  - "query.py 和 MCP Tool 的区别？" → query.py 是开发调试 CLI，MCP Tool 是生产接口
  - "为什么需要 CLI 入口？" → 快速验证检索流程，不需要启动 MCP Server
  - "argparse vs click？" → argparse 标准库无依赖
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

from core.query_engine.dense_retriever import DenseRetriever  # noqa: E402
from core.query_engine.fusion import Fusion  # noqa: E402
from core.query_engine.hybrid_search import HybridSearch  # noqa: E402
from core.query_engine.query_processor import QueryProcessor  # noqa: E402
from core.query_engine.reranker import CoreReranker  # noqa: E402
from core.query_engine.sparse_retriever import SparseRetriever  # noqa: E402
from core.settings import load_settings  # noqa: E402
from core.trace.trace_context import TraceContext  # noqa: E402

logger = logging.getLogger(__name__)


# ============================================================
# 组件初始化
# ============================================================

def create_components(settings_path: str) -> dict:
    """创建所有检索组件

    接口签名：create_components(settings_path: str) -> dict
    入参：配置文件路径
    出参：包含所有组件的 dict

    知识点：组件初始化顺序
      1. 加载配置
      2. 创建各检索组件（QueryProcessor、DenseRetriever、SparseRetriever）
      3. 创建 Fusion 和 CoreReranker
      4. 组装 HybridSearch
      5. 返回所有组件
    """
    settings = load_settings(settings_path)

    # 创建各组件
    query_processor = QueryProcessor(settings)
    dense_retriever = DenseRetriever(settings)
    sparse_retriever = SparseRetriever(settings)
    fusion = Fusion(k=60)
    reranker = CoreReranker(settings)

    # 组装 HybridSearch
    hybrid_search = HybridSearch(
        settings=settings,
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        fusion=fusion,
    )

    return {
        "settings": settings,
        "query_processor": query_processor,
        "dense_retriever": dense_retriever,
        "sparse_retriever": sparse_retriever,
        "fusion": fusion,
        "reranker": reranker,
        "hybrid_search": hybrid_search,
    }


# ============================================================
# 格式化输出
# ============================================================

def format_result(index: int, result, verbose: bool = False) -> str:
    """格式化单条检索结果

    接口签名：format_result(index, result, verbose) -> str
    入参：
      - index: 序号
      - result: RetrievalResult
      - verbose: 是否显示完整信息
    出参：格式化后的字符串
    """
    lines = []
    # 序号和分数
    lines.append(f"  [{index + 1}] score={result.score:.4f}")

    # 文本摘要（前 200 字符）
    text_preview = result.text[:200] + ("..." if len(result.text) > 200 else "")
    lines.append(f"      文本: {text_preview}")

    # 来源信息
    source = result.metadata.get("source_ref", result.metadata.get("source", "未知"))
    lines.append(f"      来源: {source}")

    # Verbose 模式显示额外信息
    if verbose:
        lines.append(f"      chunk_id: {result.chunk_id}")
        if "doc_id" in result.metadata:
            lines.append(f"      doc_id: {result.metadata['doc_id']}")
        if "title" in result.metadata:
            lines.append(f"      title: {result.metadata['title']}")
        if "page" in result.metadata:
            lines.append(f"      page: {result.metadata['page']}")

    return "\n".join(lines)


def print_results(results: list, title: str = "检索结果", verbose: bool = False) -> None:
    """打印检索结果列表

    接口签名：print_results(results, title, verbose) -> None
    """
    print(f"\n{'=' * 60}")
    print(f"{title} ({len(results)} 条)")
    print("=" * 60)

    if not results:
        print("  (无结果)")
    else:
        for i, result in enumerate(results):
            print(format_result(i, result, verbose))


def print_trace_summary(trace: TraceContext) -> None:
    """打印 trace 汇总信息

    接口签名：print_trace_summary(trace) -> None
    """
    summary = trace.finish()
    print(f"\n{'=' * 60}")
    print("Trace 汇总")
    print("=" * 60)
    print(f"  trace_id: {summary['trace_id']}")
    print(f"  总耗时: {summary['total_duration_ms']:.1f}ms")
    print(f"  阶段数: {len(summary['stages'])}")

    for stage in summary["stages"]:
        stage_name = stage["stage"]
        stage_duration = stage.get("duration_ms", "N/A")
        print(f"    - {stage_name}: {stage_duration}ms")


# ============================================================
# 主流程
# ============================================================

def run_query(
    query: str,
    top_k: int = 10,
    collection: str | None = None,
    verbose: bool = False,
    no_rerank: bool = False,
    config_path: str = "config/settings.yaml",
) -> int:
    """执行查询流程

    接口签名：run_query(query, top_k, collection, verbose, no_rerank, config_path) -> int
    入参：查询参数
    出参：退出码（0=成功，1=失败）

    处理流程：
      1. 创建组件
      2. 构建 filters
      3. 创建 TraceContext
      4. 调用 HybridSearch.search()
      5. 调用 Reranker.rerank()（除非 --no-rerank）
      6. 格式化输出结果
    """
    print(f"\n🔍 查询: {query}")
    print(f"   top_k: {top_k}, collection: {collection or '全部'}, rerank: {not no_rerank}")

    # 1. 创建组件
    try:
        components = create_components(config_path)
    except FileNotFoundError as e:
        print(f"\n❌ 初始化失败: {e}")
        print("   提示: 请先运行 ingest.py 摄取数据")
        return 1
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        return 1

    hybrid_search = components["hybrid_search"]
    reranker = components["reranker"]

    # 2. 构建 filters
    filters = {}
    if collection:
        filters["collection"] = collection

    # 3. 创建 TraceContext
    trace = TraceContext()

    # 4. 执行混合检索
    start = time.perf_counter()
    try:
        candidates = hybrid_search.search(
            query=query,
            top_k=top_k * 2,  # 留余量给 Reranker
            filters=filters if filters else None,
            trace=trace,
        )
    except RuntimeError as e:
        print(f"\n❌ 检索失败: {e}")
        return 1

    retrieval_time = (time.perf_counter() - start) * 1000

    if not candidates:
        print(f"\n⚠️ 未找到相关文档（耗时 {retrieval_time:.1f}ms）")
        print("   提示: 请先运行 ingest.py 摄取数据")
        if verbose:
            print_trace_summary(trace)
        return 0

    # 5. Reranker 精排
    if not no_rerank and reranker.is_enabled:
        rerank_start = time.perf_counter()
        results = reranker.rerank(query, candidates[:top_k * 2], trace=trace)
        rerank_time = (time.perf_counter() - rerank_start) * 1000
        # 截断到 top_k
        results = results[:top_k]
    else:
        results = candidates[:top_k]
        rerank_time = 0.0

    total_time = (time.perf_counter() - start) * 1000

    # 6. 输出结果
    print_results(results, title="最终检索结果", verbose=verbose)

    # 打印耗时
    print(f"\n  ⏱️ 检索耗时: {retrieval_time:.1f}ms", end="")
    if not no_rerank and reranker.is_enabled:
        print(f" | 精排耗时: {rerank_time:.1f}ms", end="")
    print(f" | 总耗时: {total_time:.1f}ms")

    # Verbose 模式显示 trace
    if verbose:
        print_trace_summary(trace)

    return 0


# ============================================================
# CLI 入口
# ============================================================

def main() -> int:
    """CLI 入口函数

    接口签名：main() -> int
    出参：退出码（0=成功，1=失败）
    """
    parser = argparse.ArgumentParser(
        description="RAG 查询工具 — 在线检索 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/query.py --query "如何配置 Azure？"
  python scripts/query.py --query "什么是 RAG？" --top-k 5
  python scripts/query.py --query "向量数据库" --collection default
  python scripts/query.py --query "BM25 算法" --verbose
  python scripts/query.py --query "测试" --no-rerank
        """,
    )

    parser.add_argument(
        "--query", "-q",
        type=str,
        required=True,
        help="查询文本（必填）",
    )
    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=10,
        help="返回结果数量（默认 10）",
    )
    parser.add_argument(
        "--collection", "-c",
        type=str,
        default=None,
        help="限定检索集合（可选）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示各阶段中间结果（调试用）",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="跳过 Reranker 阶段",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="配置文件路径（默认 config/settings.yaml）",
    )

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    return run_query(
        query=args.query,
        top_k=args.top_k,
        collection=args.collection,
        verbose=args.verbose,
        no_rerank=args.no_rerank,
        config_path=args.config,
    )


if __name__ == "__main__":
    sys.exit(main())

