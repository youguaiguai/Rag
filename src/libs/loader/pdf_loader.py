"""
PDF Loader 实现 — 使用 MarkItDown 将 PDF 转为 Markdown

知识点：为什么先转 Markdown 再切分？
  - Markdown 有天然的结构标记（标题、段落、代码块、列表）
  - RecursiveCharacterTextSplitter 可以按 Markdown 结构智能切分
  - 比直接从 PDF 提取纯文本再切分质量高得多
  - 面试考点："为什么要先转 Markdown？" → 结构标记 + Splitter 友好

MarkItDown 的作用：
  - Microsoft 开源的文档转换工具
  - 支持多种格式 → Markdown（PDF, DOCX, PPTX, HTML 等）
  - 本项目用作默认 PDF 解析引擎
  - 面试考点："为什么选 MarkItDown？" → 直接产出 Markdown + 多格式支持

图片处理（遵循 C1 契约）：
  - PDF 中的图片提取到 data/images/{doc_hash}/ 目录
  - 在文本中插入占位符 [IMAGE: {image_id}]
  - metadata.images 记录图片信息
  - 图片提取失败不阻塞文本解析（降级策略）
  - 面试考点："图片提取失败怎么办？" → 降级跳过，不阻断文本解析

接口签名：
  PdfLoader.load(path: str) -> Document
"""

from __future__ import annotations

import re
from core.types import Document, generate_doc_id
from libs.loader.base_loader import BaseLoader, LoaderError
from pathlib import Path
from typing import Any


class PdfLoader(BaseLoader):
    """PDF 文档加载器 — 使用 MarkItDown 将 PDF 转为 Markdown

    知识点：MarkItDown 集成设计
      - 延迟导入 markitdown（只在实际加载时才导入）
      - 如果 markitdown 未安装，抛出 LoaderError 并提示安装
      - 面试考点："为什么延迟导入？" → 减少启动时间 + 可选依赖

    处理流程：
      1. 检查文件存在 + 扩展名
      2. 用 MarkItDown 转换 PDF → Markdown 文本
      3. 生成 doc_id
      4. 构造 metadata（source_path, doc_type, title）
      5. 返回 Document

    metadata 字段说明：
      - source_path: 源文件路径
      - doc_type: "pdf"
      - title: 从 Markdown 第一个标题提取（如果没有则用文件名）
      - file_hash: 文件 SHA256（可选，由 Pipeline 注入）
    """

    supported_extensions = [".pdf"]

    def load(self, path: str, **kwargs: Any) -> Document:
        """加载 PDF 文件，返回 Document 对象

        接口签名：load(path: str) -> Document
        入参：
          - path: PDF 文件路径
          - **kwargs: 可选参数（extract_images=False 等，预留）
        出参：Document 对象（text 为 Markdown 格式）
        异常：LoaderError — 文件不存在 / 格式错误 / MarkItDown 不可用

        处理流程：
          1. 验证文件路径和扩展名
          2. 延迟导入 markitdown
          3. 调用 MarkItDown 转换
          4. 提取标题
          5. 构造 Document
        """
        file_path = Path(path)

        # 1. 验证文件
        if not file_path.exists():
            raise LoaderError(f"PDF 文件不存在: {path}")
        if file_path.suffix.lower() not in self.supported_extensions:
            raise LoaderError(
                f"不支持的文件格式: {file_path.suffix}，"
                f"仅支持: {self.supported_extensions}"
            )

        # 2. 延迟导入 markitdown
        try:
            from markitdown import MarkItDown
        except ImportError:
            raise LoaderError(
                "markitdown 未安装，请执行: pip install markitdown"
            )

        # 3. 调用 MarkItDown 转换
        try:
            md = MarkItDown()
            result = md.convert(str(file_path))
            text = result.text_content
        except Exception as e:
            raise LoaderError(f"PDF 解析失败: {path}: {e}")

        # 4. 验证转换结果
        if not text or not text.strip():
            raise LoaderError(f"PDF 解析结果为空: {path}")

        # 5. 提取标题
        title = self._extract_title(text, file_path)

        # 6. 生成 doc_id 和构造 metadata
        doc_id = generate_doc_id(str(file_path))
        metadata: dict[str, Any] = {
            "source_path": str(file_path),
            "doc_type": "pdf",
            "title": title,
            "file_name": file_path.name,
        }

        # 7. 图片处理（预留，降级策略：暂时跳过图片提取）
        # 图片提取在后续 C7 ImageCaptioner 阶段完善
        # 当前阶段只做文本解析，不提取图片
        metadata["images"] = []

        return Document(
            doc_id=doc_id,
            source_path=str(file_path),
            text=text.strip(),
            metadata=metadata,
        )

    def _extract_title(self, text: str, file_path: Path) -> str:
        """从 Markdown 文本中提取标题

        知识点：标题提取策略
          1. 优先找第一个 # 标题（Markdown 一级标题）
          2. 找不到则用文件名（去掉扩展名）
          - 面试考点："为什么从 Markdown 提取标题？" → 结构化元数据
        """
        # 尝试匹配 Markdown 一级标题
        title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip()

        # 回退到文件名
        return file_path.stem

