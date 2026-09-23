"""
ConfigService — 配置读取服务

知识点：Dashboard 配置服务
  - 封装 Settings 读取，格式化为前端展示友好的字典
  - 将 dataclass 配置转为 {component: {key: value}} 的嵌套结构
  - 面试考点："为什么要 Service 层？" → 解耦数据读取和 UI 渲染
"""

from __future__ import annotations

from typing import Any


class ConfigService:
    """配置读取服务 — 读取并格式化 Settings 配置信息

    知识点：ConfigService 的设计原则
      - 单例模式：一个 Dashboard 实例共享一个 ConfigService
      - 只读：不修改配置，只读取展示
      - 面试考点："为什么不直接读 Settings？" → Service 可缓存 + 格式化 + Mock
    """

    def __init__(self, settings: Any = None) -> None:
        """初始化 ConfigService

        入参：settings — Settings 实例。None 时自动创建。
        """
        self._settings = settings

    @property
    def settings(self) -> Any:
        """获取 Settings 实例（延迟加载）"""
        if self._settings is None:
            from core.settings import Settings
            self._settings = Settings()
        return self._settings

    def get_component_cards(self) -> dict[str, dict[str, str]]:
        """获取各组件配置卡片

        接口签名：get_component_cards() -> dict[str, dict[str, str]]
        出参：{组件名: {配置项: 值}}

        知识点：组件卡片设计
          - 每个组件一张卡片（Embedding、VectorStore、Sparse、LLM、Reranker）
          - 卡片内展示关键配置（provider、model、backend）
          - 面试考点："为什么不用表格？" → 卡片更适合展示异构配置
        """
        s = self.settings
        cards: dict[str, dict[str, str]] = {}

        # Embedding 配置
        if hasattr(s, "embedding"):
            cards["Embedding"] = {
                "Provider": getattr(s.embedding, "provider", "N/A"),
                "Model": getattr(s.embedding, "model", "N/A"),
                "Dimensions": str(getattr(s.embedding, "dimension", "N/A")),
                "Batch Size": str(getattr(s.embedding, "batch_size", "N/A")),
            }

        # Vector Store 配置
        if hasattr(s, "vector_store"):
            cards["Vector Store"] = {
                "Backend": getattr(s.vector_store, "backend", "N/A"),
                "Persistence": getattr(s.vector_store, "persist_directory", "N/A"),
                "Distance": getattr(s.vector_store, "distance_metric", "cosine"),
            }

        # Sparse 配置
        if hasattr(s, "retrieval"):
            cards["Sparse Retrieval"] = {
                "Backend": getattr(s.retrieval, "sparse_backend", "bm25"),
                "Fusion Algorithm": getattr(s.retrieval, "fusion_algorithm", "rrf"),
                "Top-K Dense": str(getattr(s.retrieval, "top_k_dense", "N/A")),
                "Top-K Sparse": str(getattr(s.retrieval, "top_k_sparse", "N/A")),
                "Top-K Final": str(getattr(s.retrieval, "top_k_final", "N/A")),
            }

        # Reranker 配置
        if hasattr(s, "rerank"):
            cards["Reranker"] = {
                "Enabled": str(getattr(s.rerank, "enabled", False)),
                "Backend": getattr(s.rerank, "backend", "N/A"),
            }

        # MCP Server 配置
        cards["MCP Server"] = {
            "Name": "modular-rag-mcp-server",
            "Version": "0.1.0",
            "Protocol": "JSON-RPC 2.0 (Stdio)",
        }

        return cards

    def get_system_info(self) -> dict[str, str]:
        """获取系统信息摘要

        接口签名：get_system_info() -> dict[str, str]
        """
        import platform
        return {
            "Python": platform.python_version(),
            "Platform": platform.platform(),
            "Project": "Modular RAG MCP Server",
            "Version": "0.1.0",
        }

