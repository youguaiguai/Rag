"""
Loader 模块 — 可插拔的文档加载抽象层

导出：
  - BaseLoader: 抽象基类，所有加载器的统一接口
  - LoaderError: 加载异常
  - LoaderFactory: 工厂类，根据文件类型创建对应实现
  - PdfLoader: PDF 加载器（MarkItDown 转换）
  - MarkdownLoader: Markdown 加载器
  - TextLoader: 纯文本加载器
  - FakeLoader: 测试桩
  - FileIntegrityChecker: SHA256 文件完整性检查器
  - FileIntegrityError: 文件完整性异常
"""

from libs.loader.base_loader import BaseLoader, LoaderError
from libs.loader.file_integrity import FileIntegrityChecker, FileIntegrityError
from libs.loader.loader_factory import (
    FakeLoader,
    LoaderFactory,
    MarkdownLoader,
    PdfLoader,
    TextLoader,
)

__all__ = [
    "BaseLoader",
    "LoaderError",
    "LoaderFactory",
    "PdfLoader",
    "MarkdownLoader",
    "TextLoader",
    "FakeLoader",
    "FileIntegrityChecker",
    "FileIntegrityError",
]

