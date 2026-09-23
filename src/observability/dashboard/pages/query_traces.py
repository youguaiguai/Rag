"""
Query Traces 页面 — 查询追踪

知识点：Query Traces 页面设计
  - 历史列表：按时间倒序展示 query trace，支持关键词搜索
  - 详情页：耗时瀑布图 + Dense vs Sparse 对比
  - 面试考点："Query Traces 的作用？" → 调试召回问题 + 性能分析

数据来源：
  - TraceService 读取 logs/traces_*.jsonl
  - F3 打点的阶段：query_processing, dense_retrieval, sparse_retrieval, fusion, rerank
"""

from __future__ import annotations

import streamlit as st


def render_query_traces() -> None:
    """渲染 Query Traces 页面

    接口签名：render_query_traces() -> None
    """
    st.title("Query Traces")
    st.markdown("查看查询历史记录、阶段耗时与检索对比")

    trace_service = _get_trace_service()
    if trace_service is None:
        st.error("无法初始化 Trace 服务")
        return

    # 搜索框
    search_keyword = st.text_input("🔍 搜索 Query 关键词", "")

    # 加载 query traces
    traces = trace_service.list_traces(trace_type="query", limit=50)

    # 过滤
    if search_keyword:
        filtered = []
        for t in traces:
            # 从 stages 中查找 query
            for stage in t.stages:
                data = stage.get("data", {})
                query_text = data.get("query", "")
                if search_keyword.lower() in str(query_text).lower():
                    filtered.append(t)
                    break
        traces = filtered

    if not traces:
        st.info("暂无查询追踪记录。请先执行查询产生 trace 数据。")
        return

    # ---- 历史列表 ----
    st.subheader("查询历史")

    for trace in traces:
        # 从 trace 中提取 query 文本
        query_text = _extract_query(trace)

        col1, col2, col3, col4 = st.columns([4, 2, 2, 1])

        with col1:
            display_query = query_text[:50] + "..." if len(query_text) > 50 else query_text
            st.text(f"🔍 {display_query or trace.trace_id[:16]}")
        with col2:
            st.text(trace.started_at[:19] if trace.started_at else "N/A")
        with col3:
            st.text(f"{trace.total_elapsed_ms:.1f}ms")
        with col4:
            if st.button("详情", key=f"q_detail_{trace.trace_id}"):
                st.session_state["selected_query_trace"] = trace.trace_id
                st.rerun()

    # ---- 详情展开 ----
    selected = st.session_state.get("selected_query_trace")
    if selected:
        _render_trace_detail(trace_service, selected)


def _extract_query(trace: Any) -> str:
    """从 trace 中提取查询文本"""
    for stage in trace.stages:
        data = stage.get("data", {})
        if "query" in data:
            return str(data["query"])
    return ""


def _render_trace_detail(trace_service: Any, trace_id: str) -> None:
    """渲染 Trace 详情

    接口签名：_render_trace_detail(trace_service, trace_id) -> None
    """
    trace = trace_service.get_trace_detail(trace_id)
    if trace is None:
        st.warning("未找到 Trace")
        return

    st.divider()
    st.subheader(f"Trace: {trace.trace_id[:20]}...")

    # 基本信息
    col1, col2, col3 = st.columns(3)
    col1.metric("Type", trace.trace_type)
    col2.metric("Duration", f"{trace.total_elapsed_ms:.1f}ms")
    col3.metric("Stages", len(trace.stages))

    # 阶段耗时瀑布图
    if trace.stages:
        st.subheader("阶段耗时")

        stage_names = []
        stage_durations = []
        for stage in trace.stages:
            name = stage.get("stage", "unknown")
            duration = stage.get("duration_ms", 0) or 0
            stage_names.append(name)
            stage_durations.append(duration)

        # 使用 Streamlit 原生 bar_chart
        import pandas as pd
        df = pd.DataFrame({
            "Duration (ms)": stage_durations,
        }, index=stage_names)

        st.bar_chart(df)

    # Dense vs Sparse 对比
    _render_dense_sparse_comparison(trace)

    # 阶段详情表格
    st.subheader("阶段详情")
    stage_data = []
    for stage in trace.stages:
        stage_data.append({
            "Stage": stage.get("stage", ""),
            "Duration (ms)": stage.get("duration_ms", 0),
            "Method": stage.get("data", {}).get("method", ""),
            "Details": str(stage.get("data", ""))[:100],
        })
    st.table(stage_data)


def _render_dense_sparse_comparison(trace: Any) -> None:
    """渲染 Dense vs Sparse 对比

    数据来源：F3 打点的 dense_retrieval 和 sparse_retrieval 阶段
    """
    dense_count = 0
    sparse_count = 0

    for stage in trace.stages:
        data = stage.get("data", {})
        if stage.get("stage") == "dense_retrieval":
            dense_count = data.get("result_count", 0)
        elif stage.get("stage") == "sparse_retrieval":
            sparse_count = data.get("result_count", 0)

    if dense_count or sparse_count:
        st.subheader("Dense vs Sparse 对比")

        col1, col2 = st.columns(2)
        col1.metric("Dense Results", dense_count)
        col2.metric("Sparse Results", sparse_count)

        # 简单对比图
        import pandas as pd
        df = pd.DataFrame({
            "Count": [dense_count, sparse_count],
        }, index=["Dense", "Sparse"])
        st.bar_chart(df)


@st.cache_resource
def _get_trace_service() -> Any:
    """获取 TraceService 实例"""
    try:
        from observability.dashboard.services.trace_service import TraceService
        return TraceService()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("TraceService 初始化失败: %s", e)
        return None

