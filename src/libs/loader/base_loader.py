"""
Loader 抽象基类 — 可插拔的文档加载接口

知识点：BaseLoader 的设计目标
  - 定义统一的文档加载接口：load(path) -> Document
  - 不同格式（PDF/Markdown/HTML）只需实现此接口即可插拔
  - Loader 只负责"格式统一 + 结构抽取"，不负责切分
  - 面试考点："Loader 的职责边界？" → 格式转换 + 结构抽取，不切分

  - 为什么需要抽象基类？
    - 不同文档格式有不同的解析方式（PDF 用 MarkItDown，Markdown 直接读文件）
    - 但上层 Pipeline 不关心格式，只想要统一的 Document 对象
    - ABC + @abstractmethod 强制子类实现 load()
    - 面试考点："为什么要抽象 BaseLoader？" → 统一接口 + 可插拔

接口签名：
  BaseLoader.load(path: str) -> Document
  BaseLoader.supported_extensions -> list[str] (property)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from core.types import Document
from typing import Any


class LoaderError(Exception):
    """Loader 异常

    知识点：自定义异常
      - 文件读取失败 / 解析失败 / 格式不支持时抛出
      - 面试考点："什么时候抛 LoaderError？" → 文件不存在 + 解析失败 + 格式不支持
    """
    pass


class BaseLoader(ABC):
    """文档加载器抽象基类

    知识点：接口设计
      - load(path) -> Document：核心方法，子类必须实现
      - supported_extensions：类属性，声明支持的文件扩展名
      - 面试考点："BaseLoader 有几个方法？" → 一个 load() + 一个 supported_extensions

    使用方式：
      loader: BaseLoader = LoaderFactory.create("pdf")
      doc = loader.load("/path/to/doc.pdf")

    子类实现示例：
      - PdfLoader: PDF → Markdown（用 MarkItDown 转换）
      - MarkdownLoader: 直接读取文件内容
      - HTMLLoader: HTML → Markdown（用 markdownify 转换）
    """

    # 子类需覆盖此属性，声明支持的文件扩展名
    supported_extensions: list[str] = []

    @abstractmethod
    def load(self, path: str, **kwargs: Any) -> Document:
        """加载文档文件，返回统一的 Document 对象

        接口签名：load(path: str) -> Document
        入参：
          - path: 文件路径
          - **kwargs: 可选参数（如图片提取开关等）
        出参：Document 对象（包含 doc_id, source_path, text, metadata）
        异常：LoaderError — 文件不存在 / 解析失败

        知识点：返回值设计
          - text: Markdown 格式的文档全文（统一中间格式）
          - metadata: 至少包含 source_path, doc_type, title
          - 面试考点："为什么 text 是 Markdown 格式？"
            → 统一中间格式 + Splitter 对 Markdown 结构友好

        子类实现要点：
          1. 读取文件
          2. 转换为 Markdown 格式
          3. 生成 doc_id（用 generate_doc_id）
          4. 构造 metadata
          5. 返回 Document
        """
        ...

