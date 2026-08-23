"""
Loader 工厂 — 根据文件类型创建对应的 Loader 实例

知识点：
  - 工厂模式：与 LLMFactory/EmbeddingFactory 同构设计
  - 路由依据：文件扩展名（.pdf → PdfLoader，.md → MarkdownLoader）
  - 面试考点："Loader 工厂怎么决定用哪个实现？" → 按文件扩展名路由

工厂路由逻辑：
  .pdf  → PdfLoader（MarkItDown 转换）
  .md   → MarkdownLoader（直接读取）
  .txt  → TextLoader（直接读取）
  fake  → FakeLoader（测试桩）

接口签名：
  LoaderFactory.create(file_type: str) -> BaseLoader
  LoaderFactory.create_for_file(path: str) -> BaseLoader
"""

from __future__ import annotations

from core.types import Document, generate_doc_id
from libs.loader.base_loader import BaseLoader, LoaderError
from libs.loader.pdf_loader import PdfLoader
from pathlib import Path
from typing import Any


# ============================================================
# FakeLoader — 测试桩
# ============================================================

class FakeLoader(BaseLoader):
    """Fake Loader 实现 — 测试专用，不读取真实文件

    知识点：测试桩 (Test Stub)
      - 不依赖真实文件系统
      - 返回预设的 Document 对象
      - 用于测试 Pipeline 编排和下游组件
      - 面试考点："为什么需要 FakeLoader？" → 隔离测试 + 不依赖文件系统

    使用场景：
      - 工厂路由测试
      - Pipeline 集成测试中替代真实 PDF 解析
      - 快速验证下游切分/编码逻辑
    """

    supported_extensions = [".fake"]

    def __init__(self, text: str = "这是一段测试文本。\n\n## 测试标题\n\n更多内容。" ) -> None:
        """初始化 FakeLoader

        接口签名：FakeLoader(text: str = "...")
        入参：text — 预设的文档文本
        """
        self._preset_text = text

    def load(self, path: str, **kwargs: Any) -> Document:
        """返回预设的 Document

        接口签名：load(path: str) -> Document
        入参：path — 文件路径（用于生成 doc_id，但不实际读取）
        出参：预设内容的 Document
        """
        file_path = Path(path)
        doc_id = generate_doc_id(str(file_path))
        return Document(
            doc_id=doc_id,
            source_path=str(file_path),
            text=self._preset_text,
            metadata={
                "source_path": str(file_path),
                "doc_type": "fake",
                "title": file_path.stem,
                "file_name": file_path.name,
                "images": [],
            },
        )


# ============================================================
# MarkdownLoader — 直接读取 Markdown 文件
# ============================================================

class MarkdownLoader(BaseLoader):
    """Markdown 加载器 — 直接读取文件内容

    知识点：Markdown 是"中间格式"
      - PdfLoader 将 PDF 转为 Markdown
      - MarkdownLoader 直接读取已有的 Markdown 文件
      - 两者产出相同格式的 Document
      - 面试考点："为什么要统一到 Markdown？" → 统一中间格式 + Splitter 友好
    """

    supported_extensions = [".md", ".markdown"]

    def load(self, path: str, **kwargs: Any) -> Document:
        """加载 Markdown 文件

        接口签名：load(path: str) -> Document
        """
        file_path = Path(path)

        if not file_path.exists():
            raise LoaderError(f"Markdown 文件不存在: {path}")

        try:
            text = file_path.read_text(encoding="utf-8")
        except IOError as e:
            raise LoaderError(f"读取 Markdown 文件失败: {path}: {e}")

        if not text.strip():
            raise LoaderError(f"Markdown 文件内容为空: {path}")

        doc_id = generate_doc_id(str(file_path))
        title = self._extract_title(text, file_path)

        return Document(
            doc_id=doc_id,
            source_path=str(file_path),
            text=text.strip(),
            metadata={
                "source_path": str(file_path),
                "doc_type": "markdown",
                "title": title,
                "file_name": file_path.name,
                "images": [],
            },
        )

    def _extract_title(self, text: str, file_path: Path) -> str:
        """从 Markdown 文本中提取标题"""
        import re
        title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip()
        return file_path.stem


# ============================================================
# TextLoader — 直接读取纯文本文件
# ============================================================

class TextLoader(BaseLoader):
    """纯文本加载器 — 读取 .txt 文件"""

    supported_extensions = [".txt"]

    def load(self, path: str, **kwargs: Any) -> Document:
        """加载文本文件"""
        file_path = Path(path)

        if not file_path.exists():
            raise LoaderError(f"文本文件不存在: {path}")

        try:
            text = file_path.read_text(encoding="utf-8")
        except IOError as e:
            raise LoaderError(f"读取文本文件失败: {path}: {e}")

        if not text.strip():
            raise LoaderError(f"文本文件内容为空: {path}")

        doc_id = generate_doc_id(str(file_path))

        return Document(
            doc_id=doc_id,
            source_path=str(file_path),
            text=text.strip(),
            metadata={
                "source_path": str(file_path),
                "doc_type": "text",
                "title": file_path.stem,
                "file_name": file_path.name,
                "images": [],
            },
        )


# ============================================================
# Loader 工厂
# ============================================================

class LoaderFactory:
    """Loader 工厂 — 根据文件类型创建对应的 Loader 实例

    接口签名：
      LoaderFactory.create(file_type: str) -> BaseLoader
      LoaderFactory.create_for_file(path: str) -> BaseLoader

    知识点：工厂模式
      - create(file_type): 按类型名创建（如 "pdf", "markdown"）
      - create_for_file(path): 按文件扩展名自动路由
      - 面试考点："为什么有两个 create 方法？" → 灵活性：显式指定 or 自动推断
    """

    _LOADERS: dict[str, type[BaseLoader]] = {
        "pdf": PdfLoader,
        "markdown": MarkdownLoader,
        "text": TextLoader,
        "fake": FakeLoader,
    }

    # 扩展名 → loader 类型名映射
    _EXT_MAP: dict[str, str] = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".fake": "fake",
    }

    @classmethod
    def create(cls, file_type: str) -> BaseLoader:
        """根据类型名创建 Loader

        接口签名：LoaderFactory.create(file_type: str) -> BaseLoader
        入参：file_type — 类型名（如 "pdf", "markdown", "text", "fake"）
        出参：BaseLoader 子类实例
        异常：LoaderError — 类型不支持

        面试考点：
          "新增格式需要改什么？" → 实现 BaseLoader + 在 _LOADERS 和 _EXT_MAP 注册
        """
        file_type = file_type.lower().strip()

        if file_type not in cls._LOADERS:
            supported = ", ".join(sorted(cls._LOADERS.keys()))
            raise LoaderError(
                f"不支持的文件类型: '{file_type}'。"
                f"当前支持: [{supported}]"
            )

        loader_class = cls._LOADERS[file_type]
        return loader_class()

    @classmethod
    def create_for_file(cls, path: str) -> BaseLoader:
        """根据文件路径的扩展名自动选择 Loader

        接口签名：LoaderFactory.create_for_file(path: str) -> BaseLoader
        入参：path — 文件路径
        出参：BaseLoader 子类实例
        异常：LoaderError — 扩展名不支持

        知识点：自动路由
          - 从路径提取扩展名 → 查 _EXT_MAP → 查 _LOADERS → 创建实例
          - 面试考点："怎么自动选 Loader？" → 扩展名映射
        """
        ext = Path(path).suffix.lower()
        file_type = cls._EXT_MAP.get(ext)

        if file_type is None:
            supported = ", ".join(sorted(cls._EXT_MAP.keys()))
            raise LoaderError(
                f"不支持的文件扩展名: '{ext}' (文件: {path})。"
                f"当前支持: [{supported}]"
            )

        return cls.create(file_type)

    @classmethod
    def register(cls, file_type: str, loader_class: type[BaseLoader], extensions: list[str] | None = None) -> None:
        """注册新的 Loader

        接口签名：LoaderFactory.register(file_type, loader_class, extensions=None) -> None

        知识点：开放-封闭原则 (OCP)
          - 对扩展开放：新增格式不改工厂代码
          - 对修改封闭：create() 方法不需要修改
        """
        if not issubclass(loader_class, BaseLoader):
            raise LoaderError(f"注册失败: {loader_class} 不是 BaseLoader 的子类")

        key = file_type.lower().strip()
        cls._LOADERS[key] = loader_class

        if extensions:
            for ext in extensions:
                cls._EXT_MAP[ext.lower()] = key

