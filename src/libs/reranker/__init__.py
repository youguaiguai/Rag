"""
Reranker 模块 — 导出核心组件

可插拔 Reranker 架构：
  BaseReranker（抽象基类） → NoneReranker（默认回退）
                         → CrossEncoderReranker（B7.8 实现）
                         → LLMReranker（B7.7 实现）

使用方式：
  from libs.reranker import RerankerFactory, BaseReranker, RerankCandidate

  settings = RerankSettings(enabled=True, backend="none")
  reranker: BaseReranker = RerankerFactory.create(settings)
  ranked = reranker.rerank("查询文本", candidates)
"""

__all__ = [
    "BaseReranker",
    "RerankCandidate",
    "RerankerError",
    "RerankerFactory",
    "NoneReranker",
]

