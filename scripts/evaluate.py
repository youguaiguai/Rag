#!/usr/bin/env python3
"""
评估运行脚本

知识点：评估运行
  - 读取 golden test set
  - 初始化 HybridSearch + Evaluator
  - 运行评估并输出报告

使用方法：
  python scripts/evaluate.py
  python scripts/evaluate.py --test-set tests/fixtures/golden_test_set.json
  python scripts/evaluate.py --evaluator custom
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG Evaluation")
    parser.add_argument("--test-set", default="tests/fixtures/golden_test_set.json")
    parser.add_argument("--evaluator", default="custom", help="Evaluator backend (custom, ragas)")
    args = parser.parse_args()

    print("=" * 50)
    print("  RAG Evaluation Runner")
    print("=" * 50)

    # 初始化
    try:
        from core.settings import Settings
        from core.query_engine.hybrid_search import HybridSearch
        from libs.evaluator.evaluator_factory import EvaluatorFactory
        from observability.evaluation.eval_runner import EvalRunner

        settings = Settings()
        # 简化：实际需要完整初始化 HybridSearch
        hybrid_search = None  # 占位
        evaluator = EvaluatorFactory.create(args.evaluator)

        print(f"Test Set: {args.test_set}")
        print(f"Evaluator: {args.evaluator}")
        print("-" * 50)

        # 运行评估
        runner = EvalRunner(hybrid_search, evaluator)
        report = runner.run(args.test_set)

        print(report.summary())

    except Exception as e:
        print(f"Evaluation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

