"""
系统总览页面 — 组件配置卡片 + 数据资产统计

知识点：Dashboard Overview 页面设计
  - 顶部：系统信息摘要
  - 中部：组件配置卡片（Embedding、VectorStore、Sparse、Reranker）
  - 底部：数据资产统计（文档数、Chunk 数、图片数）
  - 面试考点："Dashboard 的作用？" → 运维监控 + 调试 + 数据分析
"""

from __future__ import annotations

import streamlit as st
import sys
from pathlib import Path


def render_overview() -> None:
    """渲染系统总览页面

    接口签名：render_overview() -> None
    依赖：ConfigService（配置卡片）、ChromaStore（数据统计）
    """
    st.title("📊 系统总览")
    st.markdown("Modular RAG MCP Server — 组件配置与数据资产统计")

    # 延迟导入（避免启动时加载重型依赖）
    from observability.dashboard.services.config_service import ConfigService

    config_service = ConfigService()

    # ---- 系统信息 ----
    st.subheader("系统信息")
    sys_info = config_service.get_system_info()
    cols = st.columns(len(sys_info))
    for col, (key, value) in zip(cols, sys_info.items()):
        col.metric(key, value)

    st.divider()

    # ---- 组件配置卡片 ----
    st.subheader("组件配置")
    cards = config_service.get_component_cards()

    # 每行显示 2 个卡片
    card_list = list(cards.items())
    for i in range(0, len(card_list), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j < len(card_list):
                name, configs = card_list[i + j]
                with col:
                    with st.expander(f"**{name}**", expanded=True):
                        for key, value in configs.items():
                            st.text(f"{key}: {value}")

    st.divider()

    # ---- 数据资产统计 ----
    st.subheader("数据资产")
    _render_statistics()


def _render_statistics() -> None:
    """渲染数据资产统计

    知识点：数据统计来源
      - ChromaStore.get_collection_stats() → Chunk 数、Collection 数
      - ImageStorage → 图片数
      - FileIntegrityChecker → 已处理文件数
    """
    # 尝试读取统计数据
    stats = _fetch_statistics()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Collections", stats.get("collections", 0))
    col2.metric("Documents", stats.get("documents", 0))
    col3.metric("Chunks", stats.get("chunks", 0))
    col4.metric("Images", stats.get("images", 0))


def _fetch_statistics() -> dict[str, int]:
    """获取数据资产统计

    接口签名：_fetch_statistics() -> dict[str, int]
    出参：{collections, documents, chunks, images}
    """
    stats = {"collections": 0, "documents": 0, "chunks": 0, "images": 0}

    # 文件完整性统计
    try:
        from libs.loader.file_integrity import FileIntegrityChecker
        checker = FileIntegrityChecker()
        if hasattr(checker, "list_processed"):
            stats["documents"] = len(checker.list_processed())
    except Exception:
        pass

    return stats

