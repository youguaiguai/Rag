"""
Data Browser 页面 — 数据浏览器

知识点：Data Browser 页面设计
  - 左侧：文档列表（source、chunk 数）
  - 右侧：选中文档的 Chunk 详情（可折叠）
  - 图片预览：如果 chunk 含 image_refs，显示图片
  - 面试考点："Data Browser 的作用？" → 验证摄取质量 + 调试召回结果
"""

from __future__ import annotations

import streamlit as st


def render_data_browser() -> None:
    """渲染数据浏览器页面

    接口签名：render_data_browser() -> None
    """
    st.title("Data Browser")
    st.markdown("浏览已摄入的文档、Chunk 和图片")

    # 延迟导入
    from observability.dashboard.services.data_service import DataService

    data_service = _get_data_service()
    if data_service is None:
        st.error("无法初始化数据服务")
        return

    # ---- 文档列表 ----
    st.subheader("文档列表")
    docs = data_service.list_documents()

    if not docs:
        st.info("暂无数据。请先运行 `python scripts/ingest.py --path <文档路径>` 摄取数据。")
        return

    # 文档选择
    selected_source = st.selectbox(
        "选择文档",
        options=[d.source_path for d in docs],
        format_func=lambda x: f"{x} ({next(d.chunk_count for d in docs if d.source_path == x)} chunks)",
    )

    if selected_source:
        _render_document_detail(data_service, selected_source)


def _render_document_detail(data_service: Any, source_path: str) -> None:
    """渲染文档详情

    接口签名：_render_document_detail(data_service, source_path) -> None
    """
    st.divider()
    st.subheader(f"📄 {source_path}")

    chunks = data_service.get_document_chunks(source_path)
    if not chunks:
        st.warning("该文档没有 chunk 数据")
        return

    st.text(f"共 {len(chunks)} 个 chunk")

    for i, chunk in enumerate(chunks, start=1):
        with st.expander(f"**Chunk {i}** — `{chunk.chunk_id[:20]}...`", expanded=i <= 3):
            # 文本内容
            st.markdown("**内容：**")
            st.text(chunk.text[:1000] + ("..." if len(chunk.text) > 1000 else ""))

            # 元数据
            if chunk.metadata:
                st.markdown("**元数据：**")
                metadata_display = {
                    k: v for k, v in chunk.metadata.items()
                    if k not in ("source", "source_ref", "doc_id")
                }
                if metadata_display:
                    st.json(metadata_display)

            # 图片
            image_refs = chunk.metadata.get("image_refs", [])
            if isinstance(image_refs, list) and image_refs:
                st.markdown("**关联图片：**")
                for img_ref in image_refs:
                    img_path = data_service.get_image_path(img_ref)
                    if img_path:
                        st.image(img_path, caption=img_ref, width=300)


@st.cache_resource
def _get_data_service() -> Any:
    """获取 DataService 实例（缓存）

    知识点：Streamlit 缓存
      - @st.cache_resource: 缓存资源型对象（数据库连接等）
      - 避免每次页面切换重新创建连接
    """
    try:
        from core.settings import Settings
        from libs.vector_store.vector_store_factory import VectorStoreFactory
        from ingestion.storage.image_storage import ImageStorage

        settings = Settings()
        chroma = VectorStoreFactory.create(settings.vector_store)
        image_storage = ImageStorage()

        from observability.dashboard.services.data_service import DataService
        return DataService(chroma, image_storage)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("DataService 初始化失败: %s", e)
        return None

