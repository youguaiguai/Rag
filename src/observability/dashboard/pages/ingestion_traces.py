"""
Ingestion Traces 页面 — 摄取追踪

知识点：Ingestion Traces 页面设计
  - 历史列表：按时间倒序展示 ingestion 记录
  - 详情页：横向条形图展示各阶段耗时
  - 面试考点："耗时瀑布图的作用？" → 定位性能瓶颈

使用方式：
  1. 执行 ingest → 产生 trace
  2. 打开 Dashboard → 查看摄取追踪
"""

from __future__ import annotations

import streamlit as st


def render_ingestion_traces() -> None:
    """渲染 Ingestion Traces 页面

    接口签名：render_ingestion_traces() -> None
    """
    st.title("Ingestion Traces")
    st.markdown("查看摄取历史记录与各阶段耗时")

    trace_service = _get_trace_service()
    if trace_service is None:
        st.error("无法初始化 Trace 服务")
        return

    # 加载 ingestion traces
    traces = trace_service.list_traces(trace_type="ingestion", limit=50)

    if not traces:
        st.info("暂无摄取追踪记录。请先执行摄取产生 trace 数据。")
        return

    # ---- 历史列表 ----
    st.subheader("摄取历史")

    for trace in traces:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

        with col1:
            st.text(f"🔗 {trace.trace_id[:16]}...")
        with col2:
            st.text(trace.started_at[:19] if trace.started_at else "N/A")
        with col3:
            st.text(f"{trace.total_elapsed_ms:.1f}ms")
        with col4:
            if st.button("详情", key=f"detail_{trace.trace_id}"):
                st.session_state["selected_trace"] = trace.trace_id
                st.rerun()

    # ---- 详情展开 ----
    selected = st.session_state.get("selected_trace")
    if selected:
        _render_trace_detail(trace_service, selected)


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

        # 详细表格
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

