"""
Document Chunker — 业务适配器：Document → List[Chunk]

知识点：DocumentChunker 是 libs.splitter 与 Ingestion Pipeline 之间的适配器层
  - libs.splitter：纯文本切分工具（str → List[str]），不涉及业务对象
  - DocumentChunker：业务适配器（Document → List[Chunk]），添加业务逻辑

DocumentChunker 相比 libs.splitter 的 6 个增值功能：
  1. Chunk ID 生成：调用 generate_chunk_id 生成确定性 ID
  2. 元数据继承：将 Document.metadata 复制到每个 Chunk.metadata
  3. 添加 chunk_index：记录 chunk 在文档中的序号（0-based）
  4. 建立 source_ref：记录 Chunk.source_ref 指向父 Document.id
  5. 图片引用按需分发：扫描 [IMAGE: {id}] 占位符，分发到对应 chunk
  6. 类型转换：List[str] → List[Chunk] 对象

适配器模式（Adapter Pattern）：
  - 目的：将不兼容的接口（纯文本切分）适配为业务需要的接口（对象切分）
  - 好处：libs.splitter 不需要知道 Document/Chunk 的存在
  - 面试考点："为什么不在 Splitter 中直接处理 Chunk？" → 单一职责 + 可复用

接口签名：
  DocumentChunker(settings: Settings)
  split_document(document: Document) -> List[Chunk]
"""

from __future__ import annotations

import re
from core.settings import Settings, SplitterSettings
from core.types import Chunk, Document, generate_chunk_id
from libs.splitter.base_splitter import BaseSplitter, SplitterError
from libs.splitter.splitter_factory import SplitterFactory
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class ChunkingError(Exception):
    """Chunking 异常

    知识点：为什么自定义异常？
      - 将 SplitterError 等底层异常转译为业务层异常
      - 上层代码只需 except ChunkingError，不需要关心底层实现
      - 面试考点："异常转译模式" — 将底层异常包装为领域异常
    """
    pass


# ============================================================
# DocumentChunker — 业务适配器
# ============================================================

class DocumentChunker:
    """Document → List[Chunk] 业务适配器

    知识点：适配器模式
      - libs.splitter 只知道 str → List[str]
      - Pipeline 需要 Document → List[Chunk]
      - DocumentChunker 在两者之间做适配

    职责边界（面试考点）：
      - DocumentChunker 负责业务对象转换（ID、元数据、溯源、图片分发）
      - 具体的文本切分策略由 Splitter 实例决定
      - 切换切分策略只需改配置，DocumentChunker 不变

    接口签名：
      DocumentChunker(settings: Settings)
      split_document(document: Document) -> List[Chunk]
    """

    # 图片占位符正则：匹配 [IMAGE: {id}] 格式
    # 知识点：占位符设计
    #   - 格式：[IMAGE: {image_id}]
    #   - 由 PdfLoader/MarkdownLoader 在加载时插入
    #   - DocumentChunker 扫描占位符，将对应的 ImageRef 分发到 chunk
    #   - 下游 C7 ImageCaptioner 根据 chunk.metadata["images"] 定位图片路径
    _IMAGE_PATTERN = re.compile(r'\[IMAGE:\s*(\S+?)\s*\]')

    def __init__(self, settings: Settings) -> None:
        """初始化 DocumentChunker

        接口签名：DocumentChunker(settings: Settings)
        入参：
          - settings: 项目总配置（从中获取 splitter 配置）
        异常：ChunkingError — Splitter 创建失败

        知识点：为什么接受 Settings 而非 SplitterSettings？
          - DocumentChunker 是 Ingestion Pipeline 的一部分
          - Pipeline 组件统一接收 Settings，按需提取子配置
          - 好处：组件间传参统一，不需要分别传不同子配置
        """
        self._settings = settings
        try:
            self._splitter: BaseSplitter = SplitterFactory.create(settings.splitter)
        except SplitterError as e:
            raise ChunkingError(f"Splitter 创建失败: {e}") from e

    def split_document(self, document: Document) -> list[Chunk]:
        """将 Document 切分为 List[Chunk]

        接口签名：split_document(document: Document) -> List[Chunk]
        入参：Document 对象（text + metadata）
        出参：Chunk 对象列表
        异常：ChunkingError — 切分失败

        处理流程（6 步）：
          1. 调用 Splitter 切分 Document.text → List[str]（纯文本片段）
          2. 遍历每个文本片段，生成 Chunk 对象
          3. 为每个 Chunk 生成确定性 ID（generate_chunk_id）
          4. 继承 Document.metadata 到 Chunk.metadata
          5. 设置 chunk_index 和 source_ref
          6. 扫描 [IMAGE: id] 占位符，分发图片引用

        面试考点：
          "DocumentChunker 做了什么 Splitter 没做的？"
            → ID 生成 + 元数据继承 + chunk_index + source_ref + 图片分发 + 类型转换
        """
        if not document.text:
            raise ChunkingError("文档文本为空，无法切分")

        try:
            text_chunks = self._splitter.split_text(document.text)
        except SplitterError as e:
            raise ChunkingError(f"文本切分失败: {e}") from e

        if not text_chunks:
            raise ChunkingError("切分结果为空")

        chunks: list[Chunk] = []
        for index, text_chunk in enumerate(text_chunks):
            if not text_chunk.strip():
                # 跳过纯空白片段
                continue

            chunk_id = self._generate_chunk_id(document.doc_id, index, text_chunk)
            metadata = self._inherit_metadata(document, index, text_chunk)

            chunk = Chunk(
                chunk_id=chunk_id,
                doc_id=document.doc_id,
                text=text_chunk,
                index=index,
                source_ref=f"{document.source_path}#chunk={index}",
                metadata=metadata,
            )
            chunks.append(chunk)

        if not chunks:
            raise ChunkingError("切分后无有效 chunk（全部为空白）")

        return chunks

    def _generate_chunk_id(self, doc_id: str, index: int, text: str) -> str:
        """生成确定性 Chunk ID

        接口签名：_generate_chunk_id(doc_id: str, index: int, text: str) -> str
        入参：
          - doc_id: 文档 ID
          - index: chunk 序号（0-based）
          - text: chunk 文本内容
        出参：格式 "{doc_id}_{index:04d}_{content_hash[:8]}"

        知识点：ID 确定性
          - 同一 Document 对象重复切分 → 相同的 chunk ID 序列
          - 内容变更 → content_hash 变化 → 新 ID（增量更新）
          - 面试考点："为什么 ID 包含 content_hash？" → 内容变更时自动生成新 ID
        """
        return generate_chunk_id(doc_id, index, text)

    def _inherit_metadata(
        self, document: Document, chunk_index: int, chunk_text: str
    ) -> dict[str, Any]:
        """元数据继承 + 图片引用按需分发

        接口签名：_inherit_metadata(document, chunk_index, chunk_text) -> dict
        入参：
          - document: 父文档
          - chunk_index: chunk 序号
          - chunk_text: chunk 文本（用于扫描图片占位符）
        出参：继承后的 metadata dict

        知识点：元数据继承策略
          1. 深拷贝 Document.metadata（避免共享引用）
          2. 添加 chunk_index 字段
          3. 扫描 [IMAGE: {id}] 占位符，分发图片引用
          4. 无占位符的 chunk 不含 images/image_refs 字段

        图片分发逻辑（面试考点）：
          - 扫描 chunk_text 中的 [IMAGE: {id}] 占位符
          - 从 document.metadata["images"] 中提取该 chunk 引用的图片子集
          - 写入 chunk.metadata["images"]（ImageRef 子集）
          - 写入 chunk.metadata["image_refs"]（image_id 列表）
          - 不可简单整体继承或丢弃文档级 images
          - 否则下游 C7 ImageCaptioner 将无法定位图片路径
        """
        # 1. 深拷贝文档级 metadata
        metadata: dict[str, Any] = {}
        for key, value in document.metadata.items():
            # images 单独处理，不直接继承
            if key == "images":
                continue
            metadata[key] = value

        # 2. 添加 chunk_index
        metadata["chunk_index"] = chunk_index

        # 3. 图片引用按需分发
        # 知识点：图片分发逻辑
        #   - image_refs：与占位符一致（去重后），即使图片在 doc_images 中不存在
        #   - images：仅包含在 doc_images 中找到的图片子集
        #   - 无占位符的 chunk 不含 images/image_refs 字段
        image_refs_in_chunk = self._IMAGE_PATTERN.findall(chunk_text)
        if image_refs_in_chunk:
            doc_images = document.metadata.get("images", [])
            # 构建 image_id → ImageRef 映射
            image_map: dict[str, Any] = {}
            for img in doc_images:
                if isinstance(img, dict) and "image_id" in img:
                    image_map[img["image_id"]] = img

            # 提取该 chunk 引用的图片子集（去重）
            chunk_images: list[Any] = []
            chunk_image_ids: list[str] = []
            seen_ids: set[str] = set()
            for img_id in image_refs_in_chunk:
                if img_id not in seen_ids:
                    chunk_image_ids.append(img_id)
                    seen_ids.add(img_id)
                    if img_id in image_map:
                        chunk_images.append(image_map[img_id])

            metadata["images"] = chunk_images
            metadata["image_refs"] = chunk_image_ids

        return metadata

    @property
    def splitter_name(self) -> str:
        """返回当前使用的 Splitter 名称（用于日志和追踪）"""
        return self._splitter.provider_name

