"""
ImageCaptioner — Vision LLM 图片描述生成 + 降级不阻塞

知识点：Transform 链的第三个组件（C7）
  - 职责：当 Vision LLM 可用且 chunk 包含图片引用时，为图片生成文字描述
  - 降级策略：Vision LLM 不可用 / 调用失败 / 图片数据缺失 → 跳过描述，标记 has_unprocessed_images
  - 不阻塞：任何异常都不中断 ingestion pipeline（Fail-Safe）

图片描述的用途（面试考点）：
  - 多模态 RAG：图片不能直接 embed，先 captioning 转文本，再参与检索
  - 用户体验：检索结果中展示图片描述，减少用户阅读成本
  - 辅助理解：图片描述补充文本上下文，提升检索质量

图片数据来源（与 DocumentChunker 对齐）：
  - chunk.metadata["images"]: list[dict] — 每个 dict 包含 image_id, 可选 path/data(base64)
  - chunk.metadata["image_refs"]: list[str] — 图片 ID 列表
  - chunk.image_ids: list[str] — 图片 ID 列表（Chunk 字段）

接口签名：
  ImageCaptioner(settings: Settings, vision_llm: BaseVisionLLM | None = None, prompt_path: str | None = None)
  transform(chunks: list[Chunk], trace: TraceContext | None = None) -> list[Chunk]

降级矩阵：
  | 条件 | 行为 | chunk 标记 |
  |------|------|-----------|
  | vision_llm.enabled=False | 跳过 | has_unprocessed_images=True |
  | 工厂创建失败 | 跳过 | has_unprocessed_images=True |
  | 无 image_ids | 跳过（正常，无图片） | has_unprocessed_images=False |
  | 图片数据缺失 | 跳过该图 | has_unprocessed_images=True |
  | LLM 调用失败 | 跳过该图 | has_unprocessed_images=True |
  | LLM 返回空 | 跳过该图 | has_unprocessed_images=True |
  | 成功 | 写入 caption | has_unprocessed_images=False |
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import replace
from ingestion.transform.base_transform import BaseTransform, TransformError
from libs.llm.base_llm import LLMError
from libs.llm.base_vision_llm import BaseVisionLLM
from libs.llm.vision_factory import VisionLLMFactory
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from core.types import Chunk

logger = logging.getLogger(__name__)


class ImageCaptioner(BaseTransform):
    """图片描述生成器 — Vision LLM 生成 caption + 降级不阻塞

    知识点：降级策略设计
      - Vision LLM 不同于 Text LLM：成本更高、依赖外部 API、可能不支持
      - 降级不影响主流程：chunk 仍然可以参与检索（只是没有图片描述）
      - has_unprocessed_images 标记：下游可以决定是否重试或展示降级提示

    接口签名：
      ImageCaptioner(settings, vision_llm=None, prompt_path=None)
    """

    # 内置 fallback prompt（prompt 文件读取失败时使用）
    _DEFAULT_PROMPT = (
        "请描述这张图片的内容。要求：\n"
        "1. 用简洁的中文描述图片中的主要视觉元素\n"
        "2. 如果图片包含文字，请一并提取\n"
        "3. 描述控制在 50 字以内\n\n"
        "上下文文本（供参考）：\n{context}\n"
    )

    def __init__(
        self,
        settings: Settings,
        vision_llm: BaseVisionLLM | None = None,
        prompt_path: str | None = None,
    ) -> None:
        """初始化 ImageCaptioner

        接口签名：ImageCaptioner(settings, vision_llm=None, prompt_path=None)
        入参：
          - settings: 全局配置（含 vision_llm 配置 + ingestion.image_captioner 配置）
          - vision_llm: 可选的 Vision LLM 实例（测试注入优先）
          - prompt_path: 可选的 prompt 模板路径
        """
        self._settings = settings

        # Vision LLM 是否启用（由 settings.vision_llm.enabled 控制）
        self._enabled: bool = settings.vision_llm.enabled

        # prompt 路径优先级：构造参数 > 配置文件
        captioner_cfg = settings.ingestion.image_captioner
        self._prompt_path: str = prompt_path or captioner_cfg.prompt_path
        self._prompt_template: str = self._load_prompt(self._prompt_path)

        # Vision LLM 实例：注入优先；未注入且 enabled=True 时从工厂创建
        self._vision_llm: BaseVisionLLM | None = vision_llm
        if self._enabled and self._vision_llm is None:
            try:
                self._vision_llm = VisionLLMFactory.create(settings.vision_llm)
                # 工厂可能返回 NoneVisionLLM（enabled=false 的空对象）
                # 如果是 NoneVisionLLM，其 model_name 为 "none"
                if self._vision_llm.model_name == "none":
                    self._enabled = False
            except LLMError as e:
                logger.warning("ImageCaptioner: Vision LLM 创建失败，降级为禁用模式: %s", e)
                self._enabled = False
                self._vision_llm = None

    # --------------------------------------------------------
    # 主入口：transform
    # --------------------------------------------------------

    def transform(
        self,
        chunks: list[Chunk],
        trace: TraceContext | None = None,
    ) -> list[Chunk]:
        """对 chunk 列表执行图片描述生成

        接口签名：transform(chunks, trace=None) -> list[Chunk]
        出参：增强后的 Chunk 列表（新对象，输入不可变）

        异常隔离：单个 chunk 处理异常 → 保留原文 + has_unprocessed_images=True
        """
        if not isinstance(chunks, list):
            raise TransformError(f"chunks 必须是 list，得到 {type(chunks).__name__}")

        captioned: list[Chunk] = []
        for chunk in chunks:
            try:
                captioned.append(self._caption_single(chunk, trace))
            except Exception as e:  # noqa: BLE001
                logger.warning("ImageCaptioner: chunk %s 处理异常，标记未处理: %s", chunk.chunk_id, e)
                new_meta = dict(chunk.metadata)
                new_meta["caption_error"] = f"exception: {e}"
                captioned.append(
                    replace(
                        chunk,
                        metadata=new_meta,
                        has_unprocessed_images=True,
                    )
                )

        if trace is not None:
            trace.record_stage(
                "image_captioner",
                {
                    "total": len(captioned),
                    "enabled": self._enabled,
                    "chunks_with_images": sum(
                        1 for c in captioned if c.image_ids or c.metadata.get("image_refs")
                    ),
                    "chunks_with_captions": sum(
                        1 for c in captioned if c.metadata.get("image_captions")
                    ),
                    "chunks_unprocessed": sum(
                        1 for c in captioned if c.has_unprocessed_images
                    ),
                },
            )

        return captioned

    # --------------------------------------------------------
    # 单 chunk 处理
    # --------------------------------------------------------

    def _caption_single(self, chunk: Chunk, trace: TraceContext | None = None) -> Chunk:
        """处理单个 chunk：解析图片引用 → 生成描述 → 写入 metadata"""
        # 收集图片 ID（优先 image_ids 字段，其次 metadata["image_refs"]）
        image_ids = self._get_image_ids(chunk)

        # 无图片 → 正常跳过（不是降级）
        if not image_ids:
            return chunk

        # Vision LLM 不可用 → 降级标记
        if not self._enabled or self._vision_llm is None:
            return replace(chunk, has_unprocessed_images=True)

        # 获取图片数据映射
        image_map = self._build_image_map(chunk)

        # 逐图生成 caption
        captions: dict[str, str] = {}
        has_unprocessed = False

        for img_id in image_ids:
            img_data = image_map.get(img_id)

            if img_data is None:
                # 图片数据缺失 → 降级
                logger.warning("ImageCaptioner: 图片 %s 数据缺失，跳过", img_id)
                has_unprocessed = True
                continue

            # 获取 base64 数据
            image_b64 = self._get_base64(img_data, img_id)
            if not image_b64:
                logger.warning("ImageCaptioner: 图片 %s base64 编码为空，跳过", img_id)
                has_unprocessed = True
                continue

            # 调用 Vision LLM
            caption = self._generate_caption(image_b64, chunk.text, img_id, trace)

            if caption and caption.strip():
                captions[img_id] = caption.strip()
            else:
                logger.warning("ImageCaptioner: 图片 %s 描述为空，标记未处理", img_id)
                has_unprocessed = True

        # 写入 metadata
        new_metadata = dict(chunk.metadata)
        if captions:
            new_metadata["image_captions"] = captions
        if has_unprocessed:
            new_metadata["caption_fallback"] = "some_images_not_captioned"

        return replace(
            chunk,
            metadata=new_metadata,
            has_unprocessed_images=has_unprocessed,
        )

    # --------------------------------------------------------
    # 图片数据解析
    # --------------------------------------------------------

    def _get_image_ids(self, chunk: Chunk) -> list[str]:
        """收集 chunk 中的图片 ID 列表（去重，保持顺序）"""
        # 优先使用 Chunk.image_ids 字段
        ids = list(chunk.image_ids) if chunk.image_ids else []

        # 其次从 metadata["image_refs"] 获取
        meta_refs = chunk.metadata.get("image_refs", [])
        if meta_refs:
            for rid in meta_refs:
                if rid not in ids:
                    ids.append(rid)

        return ids

    def _build_image_map(self, chunk: Chunk) -> dict[str, dict[str, Any]]:
        """从 chunk.metadata["images"] 构建 image_id → image_dict 映射"""
        image_map: dict[str, dict[str, Any]] = {}
        images = chunk.metadata.get("images", [])
        if isinstance(images, list):
            for img in images:
                if isinstance(img, dict) and "image_id" in img:
                    image_map[img["image_id"]] = img
        return image_map

    def _get_base64(self, img_data: dict[str, Any], img_id: str) -> str:
        """从图片数据中提取或生成 base64 编码

        知识点：图片数据的三种来源
          1. data 字段已有 base64 → 直接使用
          2. path 字段有文件路径 → 读取文件并 base64 编码
          3. 都没有 → 返回空（降级）
        """
        # 优先使用已有的 base64 数据
        data = img_data.get("data")
        if data and isinstance(data, str) and data.strip():
            return data.strip()

        # 其次从文件路径读取
        path = img_data.get("path")
        if path:
            try:
                file_path = Path(path)
                if file_path.exists() and file_path.is_file():
                    raw = file_path.read_bytes()
                    return base64.b64encode(raw).decode("ascii")
            except OSError as e:
                logger.warning("ImageCaptioner: 图片文件读取失败 %s: %s", path, e)

        return ""

    # --------------------------------------------------------
    # Vision LLM 调用
    # --------------------------------------------------------

    def _generate_caption(
        self,
        image_b64: str,
        context_text: str,
        img_id: str,
        trace: TraceContext | None = None,
    ) -> str:
        """调用 Vision LLM 生成图片描述

        接口签名：_generate_caption(image_b64, context_text, img_id, trace) -> str
        出参：描述文本（空字符串表示失败）

        降级场景：
          1. LLMError — API 调用失败
          2. 空响应
          3. 意外异常
        """
        # 构造 prompt（注入上下文文本）
        context = context_text[:200] if context_text else ""
        prompt = self._prompt_template.replace("{context}", context)

        try:
            response = self._vision_llm.caption_image(image_b64, prompt)  # type: ignore[union-attr]
        except LLMError as e:
            logger.warning("ImageCaptioner: 图片 %s LLM 调用失败: %s", img_id, e)
            if trace is not None:
                trace.record_stage(
                    "image_captioner.llm_error",
                    {"image_id": img_id, "reason": str(e)},
                )
            return ""
        except Exception as e:  # noqa: BLE001
            logger.warning("ImageCaptioner: 图片 %s 意外异常: %s", img_id, e)
            if trace is not None:
                trace.record_stage(
                    "image_captioner.llm_error",
                    {"image_id": img_id, "reason": f"unexpected: {e}"},
                )
            return ""

        if not response or not response.strip():
            logger.warning("ImageCaptioner: 图片 %s LLM 返回空", img_id)
            return ""

        return response.strip()

    # --------------------------------------------------------
    # Prompt 加载
    # --------------------------------------------------------

    def _load_prompt(self, prompt_path: str | None = None) -> str:
        """从文件加载 prompt 模板（支持默认 fallback）"""
        if prompt_path:
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    return content
                logger.warning("ImageCaptioner: prompt 文件为空: %s，使用内置默认", prompt_path)
            except OSError as e:
                logger.warning(
                    "ImageCaptioner: prompt 文件读取失败: %s (%s)，使用内置默认",
                    prompt_path,
                    e,
                )
        return self._DEFAULT_PROMPT

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """是否启用图片描述"""
        return self._enabled

    @property
    def prompt_template(self) -> str:
        """当前使用的 prompt 模板"""
        return self._prompt_template

