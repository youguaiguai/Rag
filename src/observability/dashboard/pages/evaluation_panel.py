"""
Evaluation Panel 页面 — RAG 评估面板

知识点：Evaluation Panel 页面设计
  - 选择评估后端（如 ragas）与 golden test set
  - 运行评估 → 展示指标（hit_rate、mrr、各 query 明细）
  - 可选：历史评估结果对比图
  - 前置依赖：H3（EvalRunner）完整后才可实际运行
  - 面试考点："评估体系的价值？" → 量化 RAG 回归 + 持续改进
"""

from __future__ import annotations

import streamlit as st


def render_evaluation_panel() -> None:
    """渲染 Evaluation Panel 页面

    接口签名：render_evaluation_panel() -> None
    """
    st.title("Evaluation")
    st.markdown("运行 RAG 评估、查看指标、对比历史结果")

    # 配置选项
    st.subheader("评估配置")

    col1, col2 = st.columns(2)
    with col1:
        evaluator_backend = st.selectbox(
            "评估后端",
            options=["ragas", "custom"],
            help="选择评估框架",
        )
    with col2:
        test_set_path = st.text_input(
            "测试集路径",
            value="tests/fixtures/golden_test_set.json",
            help="Golden test set JSON 文件路径",
        )

    # 运行评估
    if st.button("运行评估", type="primary"):
        _run_evaluation(evaluator_backend, test_set_path)

    st.divider()

    # 历史结果
    st.subheader("评估历史")
    st.info("暂无历史评估记录")


def _run_evaluation(backend: str, test_set_path: str) -> None:
    """运行评估

    接口签名：_run_evaluation(backend, test_set_path) -> None
    """
    # 检查 H3 (EvalRunner) 是否可用
    try:
        from observability.evaluation.eval_runner import EvalRunner
    except ImportError:
        st.warning("EvalRunner 尚未实现 (H3 阶段)。请先完成 H3 评估体系开发。")
        return

    try:
        from core.settings import Settings
        from core.query_engine.hybrid_search import HybridSearch
        from observability.evaluation.composite_evaluator import CompositeEvaluator

        settings = Settings()
        # 这里简化处理，实际需要完整的组件初始化
        st.info(f"正在运行 {backend} 评估...")
        st.success("评估完成（演示模式）")

    except Exception as e:
        st.error(f"评估运行失败: {e}")

