"""
Transform 抽象基类 — Ingestion Pipeline 的"增强"环节

知识点：Transform 是 Pipeline 中的"增强"环节
  - 原子化：每个 Transform 只做一件事（ChunkRefiner 去噪 / MetadataEnricher 补元数据 / ImageCaptioner 生成描述）
  - 幂等性：重复执行结果不变（同样的输入 chunk 列表，同样的输出）
  - 降级安全：失败不阻塞 Pipeline，只记录警告（Fail-Safe 而非 Fail-Fast）

责任链模式（Chain of Responsibility）：
  - 多个 Transform 串联：chunks → ChunkRefiner → MetadataEnricher → ImageCaptioner
  - 每个 Transform 接收 List[Chunk] 返回 List[Chunk]
  - Pipeline 负责编排，Transform 之间互不感知
  - 面试考点："为什么 Transform 输入输出都是 List[Chunk]？" → 支持链式编排

接口签名：
  BaseTransform.transform(chunks: list[Chunk], trace: TraceContext | None) -> list[Chunk]

设计原则：
  - 接口最小化：只有 transform() 一个核心方法
  - trace 可选传入：不传也能工作（向后兼容），传入则记录阶段数据
  - 子类必须保证：不修改输入的 Chunk 对象（返回新对象或新列表）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.trace.trace_context import TraceContext
    from core.types import Chunk


# ============================================================
# 自定义异常
# ============================================================

class TransformError(Exception):
    """Transform 异常

    知识点：Transform 的异常设计哲学
      - Transform 链中的组件应该"降级安全"：
        单个 chunk 处理失败 → 保留原文，不阻塞 Pipeline
        整体输入无效（如非 list） → 抛 TransformError
      - 面试考点："Transform 什么时候抛异常？" → 只有输入整体无效时才抛
    """
    pass


# ============================================================
# BaseTransform 抽象基类
# ============================================================

class BaseTransform(ABC):
    """Transform 抽象基类 — 所有 Chunk 增强组件的统一接口

    接口签名：
      transform(chunks: list[Chunk], trace: TraceContext | None = None) -> list[Chunk]

    实现类（C5-C7）：
      - ChunkRefiner（C5）：规则去噪 + 可选 LLM 增强
      - MetadataEnricher（C6）：title/summary/tags 元数据增强
      - ImageCaptioner（C7）：Vision LLM 生成图片描述

    子类契约（面试考点）：
      1. 不修改输入的 Chunk 对象（不可变性）
      2. 输出数量与输入数量一致（Transform 不做过滤，过滤由 Pipeline 决定）
      3. 单个 chunk 失败 → 保留原文 + metadata 标记，不抛异常
      4. trace 非空时记录阶段数据
    """

    @abstractmethod
    def transform(
        self,
        chunks: list[Chunk],
        trace: TraceContext | None = None,
    ) -> list[Chunk]:
        """对 chunk 列表进行增强处理

        接口签名：transform(chunks, trace=None) -> list[Chunk]
        入参：
          - chunks: 待增强的 Chunk 列表
          - trace: 可选的追踪上下文（记录阶段数据）
        出参：增强后的 Chunk 列表（新对象）
        异常：TransformError — 输入整体无效（如非列表）

        知识点：为什么 trace 是可选参数？
          - 向后兼容：不传 trace 的调用方（如简单测试）也能工作
          - 生产环境：Pipeline 统一传入 trace，实现全链路追踪
          - 面试考点："可选参数注入 trace" → 依赖注入 (DI) 的轻量实现
        """
        ...

