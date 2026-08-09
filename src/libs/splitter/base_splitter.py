"""
Splitter 抽象基类 — 可插拔架构的核心

知识点：
  - Splitter 是什么：将长文本切分为多个 Chunk（文本片段），是 Ingestion Pipeline 的核心环节
  - ABC (Abstract Base Class)：Python 标准库提供的抽象基类机制，强制子类实现 split_text()
  - 可插拔架构：上层代码只依赖 BaseSplitter 接口，不关心底层用的是哪种切分策略
  - 工厂模式配合：SplitterFactory.create(settings) 根据 provider 字段创建具体实现

关键接口签名（面试必须掌握）：
  BaseSplitter.split_text(text: str) -> list[str]
    入参：
      - text: 原始文本（如 Markdown 文档内容）
    出参：切分后的文本片段列表（Chunk 列表）
    异常：子类实现中可能抛出 SplitterError

  BaseSplitter.provider_name -> str
    属性：返回当前切分策略名称（用于日志和追踪）

设计原则：
  - 接口最小化：只暴露 split_text() 一个核心方法 + 一个只读属性
  - 纯文本输入输出：split_text 接受 str 返回 list[str]，不涉及业务对象（Document/Chunk）
    业务对象转换由上层 DocumentChunker（C4 阶段）负责
  - 异常统一：子类应将切分过程中的异常转换为 SplitterError

面试考点：
  - "为什么要切分？" → LLM 上下文有限 + Embedding 有最大输入长度 + 检索粒度需要控制
  - "chunk_size 和 chunk_overlap 的作用？" → 控制每个片段长度 + 保留上下文连续性
  - "常见的切分策略？" → 固定长度 / 递归字符 / 语义切分 / 结构感知
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class SplitterError(Exception):
    """Splitter 切分异常

    知识点：为什么自定义异常？
      - 统一不同切分策略的异常类型
      - 上层代码只需 except SplitterError，不需要关心底层实现
      - 面试考点："异常转译模式" — 将底层异常包装为领域异常
    """
    pass


# ============================================================
# BaseSplitter 抽象基类
# ============================================================

class BaseSplitter(ABC):
    """Splitter 抽象基类 — 所有文本切分策略的统一接口

    接口签名：
      split_text(text: str) -> list[str]
      provider_name -> str (property)

    使用方式（上层代码不关心具体切分策略）：
      splitter: BaseSplitter = SplitterFactory.create(settings)
      chunks = splitter.split_text(long_document_text)

    知识点：为什么用 ABC 而不是普通继承？
      - ABC + @abstractmethod 强制子类实现 split_text()，忘记实现会 TypeError
      - 普通继承没有这个约束，运行时才发现漏实现
      - 面试考点："ABC 的作用？" → 编译期约束 + 类型安全 + 接口契约

    职责边界（面试考点）：
      - libs.splitter：纯文本切分工具（str → list[str]），不涉及业务对象
      - DocumentChunker（C4）：业务适配器（Document → list[Chunk]），添加业务逻辑
      - 这种分离遵循单一职责原则（SRP）
    """

    @abstractmethod
    def split_text(self, text: str, **kwargs: Any) -> list[str]:
        """将长文本切分为多个文本片段（Chunk）

        接口签名：split_text(text: str, **kwargs) -> list[str]
        入参：
          - text: 原始文本（如 Markdown 文档全文）
          - **kwargs: 可选参数（预留扩展）
        出参：切分后的文本片段列表
        异常：SplitterError — 切分失败 / 输入无效

        知识点：为什么接受 str 而非文件路径？
          - 职责分离：Splitter 只负责切分文本，文件读取由 Loader 负责
          - 可测试性：直接传字符串测试，不需要真实文件
          - 面试考点："为什么 split_text 接受 str 而非文件路径？" → 单一职责

        返回值结构：
          text = "# 标题\\n\\n第一段...\\n\\n第二段..."
          chunks = split_text(text)
          # chunks = ["# 标题\\n\\n第一段...", "第二段..."]
          # 每个 chunk 是一个自包含的语义单元
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """返回当前切分策略名称（用于日志和追踪）

        接口签名：provider_name -> str (property)
        示例：'recursive', 'semantic', 'fixed', 'fake'
        """
        ...

