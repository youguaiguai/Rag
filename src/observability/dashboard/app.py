"""
Streamlit Dashboard 入口 — 多页面导航架构

知识点：Dashboard 架构设计
  - st.navigation() 注册多个页面（Streamlit 1.30+ 多页面应用）
  - 每个页面是一个函数（render_xxx）
  - 未完成页面显示占位提示
  - 面试考点："Dashboard 的作用？" → 运维监控 + 数据分析 + 调试
"""

from __future__ import annotations

import streamlit as st

# 页面配置（必须在最前面调用）
st.set_page_config(
    page_title="Modular RAG Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- 导入页面渲染函数 ----
from observability.dashboard.pages.overview import render_overview
from observability.dashboard.pages.query_traces import render_query_traces
from observability.dashboard.pages.ingestion_traces import render_ingestion_traces
from observability.dashboard.pages.data_browser import render_data_browser
from observability.dashboard.pages.ingestion_manager import render_ingestion_manager
from observability.dashboard.pages.evaluation_panel import render_evaluation_panel


# ---- 页面定义 ----
PAGES = {
    "Overview": st.Page(render_overview, title="📊 Overview", default=True),
    "Query Traces": st.Page(render_query_traces, title="🔍 Query Traces"),
    "Ingestion Traces": st.Page(render_ingestion_traces, title="📥 Ingestion Traces"),
    "Data Browser": st.Page(render_data_browser, title="🗂️ Data Browser"),
    "Ingestion Manager": st.Page(render_ingestion_manager, title="⚙️ Ingestion Manager"),
    "Evaluation": st.Page(render_evaluation_panel, title="📈 Evaluation"),
}


def main() -> None:
    """Dashboard 主入口

    流程：
      1. 注册所有页面
      2. 渲染导航 + 当前选中的页面
    """
    pg = st.navigation(list(PAGES.values()))
    pg.run()


if __name__ == "__main__":
    main()

