"""
多模态内容组装 — Text + Image Base64 编码

知识点：MCP 协议支持 TextContent + ImageContent 混合返回
  - 文本内容：Markdown 格式的答案 + Citation
  - 图片内容：Base64 编码的图片数据
  - 兼容原则：第一项始终是文本，图片作为补充

MCP ImageContent 格式：
  {
    "type": "image",
    "data": "<base64-encoded-image>",
    "mimeType": "image/png"
  }

接口签名：
  MultimodalAssembler.assemble(retrieval_results, text_content) -> list[dict]
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MultimodalAssembler:
    """多模态内容组装器 — 将图片引用转换为 MCP ImageContent"""

    def assemble(
        self,
        retrieval_results: list[Any],
        text_content: str,
    ) -> list[dict[str, Any]]:
        """组装多模态内容数组

        接口签名：assemble(retrieval_results, text_content) -> list[dict]
        出参：MCP content 数组，第一项是 text，后续是 image
        """
        content: list[dict[str, Any]] = [
            {"type": "text", "text": text_content},
        ]

        image_refs = self._extract_image_refs(retrieval_results)

        for image_ref in image_refs:
            image_content = self._load_image_base64(image_ref)
            if image_content is not None:
                content.append(image_content)

        return content

    def _extract_image_refs(self, retrieval_results: list[Any]) -> list[str]:
        """从检索结果中提取去重后的图片引用列表"""
        refs: list[str] = []

        for result in retrieval_results:
            metadata = getattr(result, "metadata", {}) or {}

            # image_refs（列表格式）
            image_refs = metadata.get("image_refs")
            if isinstance(image_refs, list):
                refs.extend(image_refs)
            elif isinstance(image_refs, str):
                refs.append(image_refs)

            # 单个 image_id（兼容格式）
            image_id = metadata.get("image_id")
            if isinstance(image_id, str):
                refs.append(image_id)

        # 去重保持顺序
        return list(dict.fromkeys(refs))

    def _load_image_base64(self, image_ref: str) -> dict[str, Any] | None:
        """加载图片并编码为 base64

        接口签名：_load_image_base64(image_ref) -> dict | None
        入参：图片引用（image_id 或文件路径）
        出参：MCP ImageContent 字典，或 None（加载失败时）

        加载策略：
          1. 如果 image_ref 是绝对/相对路径 → 直接读取文件
          2. 如果 image_ref 是 image_id → 通过 ImageStorage 查找路径
          3. 失败时返回 None（不中断整个响应，失败隔离）
        """
        try:
            # 尝试作为文件路径
            path = Path(image_ref)
            if not path.is_absolute():
                # 相对路径：尝试在 data/images/ 下查找
                path = Path("data/images") / image_ref

            if path.exists() and path.is_file():
                return self._encode_image_file(path)

            # 作为 image_id 查找
            return self._load_by_image_id(image_ref)

        except Exception as e:
            logger.warning("加载图片失败: %s, error=%s", image_ref, e)
            return None

    def _encode_image_file(self, path: Path) -> dict[str, Any] | None:
        """将图片文件编码为 base64

        接口签名：_encode_image_file(path) -> dict | None
        入参：图片文件路径
        出参：MCP ImageContent 字典
        """
        try:
            raw_data = path.read_bytes()
            b64_data = base64.b64encode(raw_data).decode("ascii")

            # 猜测 MIME 类型
            mime_type = mimetypes.guess_type(str(path))[0] or "image/png"

            return {
                "type": "image",
                "data": b64_data,
                "mimeType": mime_type,
            }

        except Exception as e:
            logger.warning("编码图片失败: %s, error=%s", path, e)
            return None

    def _load_by_image_id(self, image_id: str) -> dict[str, Any] | None:
        """通过 image_id 从 ImageStorage 加载图片

        接口签名：_load_by_image_id(image_id) -> dict | None
        入参：图片 ID
        出参：MCP ImageContent 字典
        """
        try:
            from ingestion.storage.image_storage import ImageStorage

            storage = ImageStorage()
            file_path = storage.get_path(image_id)

            if file_path:
                return self._encode_image_file(Path(file_path))

            logger.debug("ImageStorage 中未找到: %s", image_id)
            return None

        except Exception as e:
            logger.warning("通过 image_id 加载图片失败: %s, error=%s", image_id, e)
            return None

