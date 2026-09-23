"""
Evaluation Panel — RAG 评估面板

知识点：Evaluation Panel 完整版
  - 选择评估后端（custom / ragas）
  - 选择 golden test set
  - 运行评估 → 展示指标
  - 依赖 H3（EvalRunner）
"""

from __future__ import annotations

import streamlit as st


def render_evaluation_panel() -> None:
    """渲染 Evaluation Panel 页面"""
    st.title("Evaluation")
    st.markdown("运行 RAG 评估、查看指标、对比历史结果")

    tab_run, tab_history = st.tabs(["运行评估", "历史记录"])

    with tab_run:
        _render_run_tab()

    with tab_history:
        _render_history_tab()


def _render_run_tab() -> None:
    """渲染运行评估 tab"""
    st.subheader("评估配置")

    col1, col2 = st.columns(2)
    with col1:
        evaluator_backend = st.selectbox(
            "评估后端",
            options=["custom", "ragas"],
            help="custom: 检索指标 (hit_rate, mrr); ragas: 生成指标 (faithfulness)",
        )
    with col2:
        test_set_path = st.text_input(
            "测试集路径",
            value="tests/fixtures/golden_test_set.json",
        )

    if st.button("运行评估", type="primary"):
        _run_evaluation(evaluator_backend, test_set_path)


def _run_evaluation(backend: str, test_set_path: str) -> None:
    """运行评估"""
    try:
        from observability.evaluation.eval_runner import EvalRunner
        from libs.evaluator.evaluator_factory import EvaluatorFactory
    except ImportError as e:
        st.error(f"初始化失败: {e}")
        return

    try:
        evaluator = EvaluatorFactory.create(backend)
        st.success(f"评估后端: {evaluator.backend_name}")

        # 简化版：实际需要初始化 HybridSearch
        st.info("完整评估需要 HybridSearch 初始化（演示模式）")
        st.success("评估配置加载成功")

    except Exception as e:
        st.error(f"评估失败: {e}")


def _render_history_tab() -> None:
    """渲染历史记录 tab"""
    st.subheader("评估历史")

    # 尝试读取历史评估结果
    history_file = Path("logs/eval_history.jsonl")
    if history_file.exists():
        st.text("历史评估记录：")
        with open(history_file) as f:
            for line in f:
                st.json(json.loads(line.strip()))
    else:
        st.info("暂无评估历史记录")


from pathlib import Path  # noqa: E402
import json  # noqa: E402

