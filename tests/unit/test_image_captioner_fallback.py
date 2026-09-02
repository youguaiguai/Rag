"""
ImageCaptioner 单元测试 — C7: Vision LLM 生成 caption + 降级不阻塞

测试策略：
  - 使用 MockVisionLLM 隔离，不依赖真实 API
  - 验收标准全覆盖：
    1. 启用模式：存在 image_refs 时生成 caption 并写入 metadata
    2. 降级模式：禁用/异常时 chunk 保留 image_refs，标记 has_unprocessed_images
    3. 无图片：正常跳过
    4. 异常隔离：单个 chunk 异常不影响其他 chunk

测试分类（20 个）：
  - BaseTransform 继承 + 基础（2）
  - 启用模式（4）
  - 降级模式（4）
  - 无图片跳过（2）
  - 图片数据解析（3）
  - 异常隔离（2）
  - 配置 + prompt（2）
  - Trace（1）
"""

from __future__ import annotations

import base64
import pytest
from core.settings import Settings, VisionLLMSettings, ImageCaptionerSettings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.base_transform import BaseTransform, TransformError
from ingestion.transform.image_captioner import ImageCaptioner
from libs.llm.base_llm import LLMError
from libs.llm.base_vision_llm import BaseVisionLLM
from pathlib import Path
from typing import Any


# ============================================================
# MockVisionLLM — 可编程测试桩
# ============================================================

class MockVisionLLM(BaseVisionLLM):
    """可编程 Mock Vision LLM — 记录调用 + 可配置返回值/异常"""

    def __init__(
        self,
        response: str = "这是一张架构图，展示系统模块组成。",
        error: Exception | None = None,
    ) -> None:
        self._model = "mock-vision-model"
        self._provider = "mock"
        self._response = response
        self._error = error
        self.calls: list[tuple[str, str]] = []  # (image_base64, prompt)

    def caption_image(self, image_base64: str, prompt: str = "", **kwargs: Any) -> str:
        self.calls.append((image_base64, prompt))
        if self._error is not None:
            raise self._error
        return self._response

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider


# ============================================================
# 辅助函数
# ============================================================

PROMPT_PATH = Path(__file__).parent.parent.parent / "config" / "prompts" / "image_captioning.txt"


def _make_settings(vision_enabled: bool = False) -> Settings:
    """创建测试用 Settings"""
    s = Settings()
    s.vision_llm.enabled = vision_enabled
    return s


def _make_chunk(
    text: str = "示例文本",
    chunk_id: str = "c_0001",
    image_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Chunk:
    """创建测试用 Chunk"""
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc123",
        text=text,
        index=0,
        source_ref=f"/test.md#chunk=0",
        metadata=metadata or {},
        image_ids=image_ids or [],
    )


def _make_image_dict(image_id: str, data: str | None = None, path: str | None = None) -> dict[str, Any]:
    """创建图片数据字典"""
    d: dict[str, Any] = {"image_id": image_id}
    if data is not None:
        d["data"] = data
    if path is not None:
        d["path"] = path
    return d


# ============================================================
# BaseTransform 继承 + 基础（2 个）
# ============================================================

class TestInheritance:

    def test_is_base_transform(self):
        """ImageCaptioner 是 BaseTransform 的子类"""
        captioner = ImageCaptioner(_make_settings())
        assert isinstance(captioner, BaseTransform)

    def test_transform_empty_list(self):
        """空列表输入 → 空列表输出"""
        captioner = ImageCaptioner(_make_settings())
        result = captioner.transform([])
        assert result == []


# ============================================================
# 启用模式（4 个）
# ============================================================

class TestEnabledMode:

    def test_generates_caption_with_image_data(self):
        """启用 + 有图片数据 → 生成 caption 并写入 metadata"""
        mock_vllm = MockVisionLLM(response="这是一张流程图。")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"fake_image_data").decode("ascii")
        chunk = _make_chunk(
            image_ids=["img_001"],
            metadata={
                "image_refs": ["img_001"],
                "images": [_make_image_dict("img_001", data=img_b64)],
            },
        )
        result = captioner.transform([chunk])

        assert result[0].metadata["image_captions"]["img_001"] == "这是一张流程图。"
        assert result[0].has_unprocessed_images is False
        assert len(mock_vllm.calls) == 1

    def test_caption_uses_context_text(self):
        """prompt 中注入了 chunk 上下文文本"""
        mock_vllm = MockVisionLLM(response="描述")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"data").decode("ascii")
        chunk = _make_chunk(
            text="这是一段关于系统架构的文本。",
            image_ids=["img_1"],
            metadata={
                "images": [_make_image_dict("img_1", data=img_b64)],
            },
        )
        captioner.transform([chunk])

        # 验证 prompt 中包含上下文文本
        _, prompt = mock_vllm.calls[0]
        assert "系统架构" in prompt

    def test_multiple_images_all_captioned(self):
        """多张图片 → 全部生成 caption"""
        mock_vllm = MockVisionLLM(response="图片描述")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"data").decode("ascii")
        chunk = _make_chunk(
            image_ids=["img_1", "img_2"],
            metadata={
                "image_refs": ["img_1", "img_2"],
                "images": [
                    _make_image_dict("img_1", data=img_b64),
                    _make_image_dict("img_2", data=img_b64),
                ],
            },
        )
        result = captioner.transform([chunk])

        assert len(result[0].metadata["image_captions"]) == 2
        assert "img_1" in result[0].metadata["image_captions"]
        assert "img_2" in result[0].metadata["image_captions"]
        assert len(mock_vllm.calls) == 2

    def test_image_from_file_path(self, tmp_path):
        """图片数据来自文件路径 → 读取并 base64 编码"""
        # 创建临时图片文件
        img_file = tmp_path / "test_image.png"
        img_file.write_bytes(b"fake_png_data")

        mock_vllm = MockVisionLLM(response="从文件读取的图片")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        chunk = _make_chunk(
            image_ids=["img_file"],
            metadata={
                "image_refs": ["img_file"],
                "images": [_make_image_dict("img_file", path=str(img_file))],
            },
        )
        result = captioner.transform([chunk])

        assert result[0].metadata["image_captions"]["img_file"] == "从文件读取的图片"
        assert len(mock_vllm.calls) == 1


# ============================================================
# 降级模式（4 个）
# ============================================================

class TestFallbackMode:

    def test_disabled_marks_unprocessed(self):
        """Vision LLM 禁用 → 标记 has_unprocessed_images"""
        settings = _make_settings(vision_enabled=False)
        captioner = ImageCaptioner(settings)

        chunk = _make_chunk(
            image_ids=["img_001"],
            metadata={"image_refs": ["img_001"]},
        )
        result = captioner.transform([chunk])

        assert result[0].has_unprocessed_images is True
        assert "image_captions" not in result[0].metadata
        # image_refs 保留
        assert result[0].metadata["image_refs"] == ["img_001"]

    def test_llm_error_marks_unprocessed(self):
        """LLM 调用失败 → 标记 has_unprocessed_images"""
        mock_vllm = MockVisionLLM(error=LLMError("API timeout"))
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"data").decode("ascii")
        chunk = _make_chunk(
            image_ids=["img_001"],
            metadata={
                "image_refs": ["img_001"],
                "images": [_make_image_dict("img_001", data=img_b64)],
            },
        )
        result = captioner.transform([chunk])

        assert result[0].has_unprocessed_images is True
        assert "image_captions" not in result[0].metadata

    def test_empty_response_marks_unprocessed(self):
        """LLM 返回空 → 标记 has_unprocessed_images"""
        mock_vllm = MockVisionLLM(response="  ")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"data").decode("ascii")
        chunk = _make_chunk(
            image_ids=["img_001"],
            metadata={
                "image_refs": ["img_001"],
                "images": [_make_image_dict("img_001", data=img_b64)],
            },
        )
        result = captioner.transform([chunk])

        assert result[0].has_unprocessed_images is True

    def test_missing_image_data_marks_unprocessed(self):
        """图片数据缺失 → 标记 has_unprocessed_images"""
        mock_vllm = MockVisionLLM(response="描述")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        # image_refs 有引用，但 images 列表为空（数据缺失）
        chunk = _make_chunk(
            image_ids=["img_missing"],
            metadata={"image_refs": ["img_missing"]},
        )
        result = captioner.transform([chunk])

        assert result[0].has_unprocessed_images is True
        assert len(mock_vllm.calls) == 0  # 没有调用 LLM


# ============================================================
# 无图片跳过（2 个）
# ============================================================

class TestNoImages:

    def test_no_images_passes_through(self):
        """无图片的 chunk → 原样返回（has_unprocessed_images=False）"""
        mock_vllm = MockVisionLLM()
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        chunk = _make_chunk(text="纯文本 chunk，没有图片。")
        result = captioner.transform([chunk])

        assert result[0].has_unprocessed_images is False
        assert len(mock_vllm.calls) == 0

    def test_empty_image_ids_passes_through(self):
        """image_ids 为空列表 → 原样返回"""
        captioner = ImageCaptioner(_make_settings(vision_enabled=True))
        chunk = _make_chunk(image_ids=[])
        result = captioner.transform([chunk])
        assert result[0].has_unprocessed_images is False


# ============================================================
# 图片数据解析（3 个）
# ============================================================

class TestImageResolution:

    def test_data_field_takes_priority_over_path(self, tmp_path):
        """data 字段优先于 path 字段"""
        img_file = tmp_path / "img.png"
        img_file.write_bytes(b"file_data")

        mock_vllm = MockVisionLLM(response="描述")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"data_field").decode("ascii")
        chunk = _make_chunk(
            image_ids=["img_1"],
            metadata={
                "image_refs": ["img_1"],
                "images": [_make_image_dict("img_1", data=img_b64, path=str(img_file))],
            },
        )
        captioner.transform([chunk])

        # 验证使用的是 data 字段的值
        received_b64, _ = mock_vllm.calls[0]
        decoded = base64.b64decode(received_b64)
        assert decoded == b"data_field"

    def test_nonexistent_path_returns_empty(self):
        """路径不存在 → 返回空，标记未处理"""
        mock_vllm = MockVisionLLM(response="描述")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        chunk = _make_chunk(
            image_ids=["img_1"],
            metadata={
                "image_refs": ["img_1"],
                "images": [_make_image_dict("img_1", path="/nonexistent/img.png")],
            },
        )
        result = captioner.transform([chunk])

        assert result[0].has_unprocessed_images is True
        assert len(mock_vllm.calls) == 0

    def test_image_ids_from_metadata_image_refs(self):
        """从 metadata["image_refs"] 获取图片 ID（chunk.image_ids 为空时）"""
        mock_vllm = MockVisionLLM(response="描述")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"data").decode("ascii")
        chunk = _make_chunk(
            image_ids=[],  # 空列表
            metadata={
                "image_refs": ["from_meta"],
                "images": [_make_image_dict("from_meta", data=img_b64)],
            },
        )
        result = captioner.transform([chunk])

        assert "from_meta" in result[0].metadata["image_captions"]
        assert len(mock_vllm.calls) == 1


# ============================================================
# 异常隔离（2 个）
# ============================================================

class TestExceptionIsolation:

    def test_single_chunk_exception_isolated(self, monkeypatch):
        """单个 chunk 处理异常 → 标记 has_unprocessed_images，不影响其他 chunk"""
        captioner = ImageCaptioner(_make_settings(vision_enabled=False))

        original = captioner._caption_single

        def flaky_single(chunk, trace=None):
            if "BOOM" in chunk.text:
                raise RuntimeError("simulated error")
            return original(chunk, trace)

        monkeypatch.setattr(captioner, "_caption_single", flaky_single)

        chunks = [
            _make_chunk("正常 chunk", chunk_id="c1"),
            _make_chunk("BOOM chunk", chunk_id="c2", image_ids=["img1"],
                        metadata={"image_refs": ["img1"]}),
            _make_chunk("另一个正常", chunk_id="c3"),
        ]
        result = captioner.transform(chunks)

        assert len(result) == 3
        assert result[0].has_unprocessed_images is False
        assert result[1].has_unprocessed_images is True
        assert "caption_error" in result[1].metadata
        assert result[2].has_unprocessed_images is False

    def test_non_list_input_raises(self):
        """非 list 输入 → 抛 TransformError"""
        captioner = ImageCaptioner(_make_settings())
        with pytest.raises(TransformError):
            captioner.transform("not a list")  # type: ignore[arg-type]


# ============================================================
# 配置 + prompt（2 个）
# ============================================================

class TestConfigAndPrompt:

    def test_settings_yaml_loads_image_captioner(self):
        """settings.yaml 的 ingestion.image_captioner 配置加载正确"""
        from core.settings import load_settings
        settings = load_settings("config/settings.yaml")

        assert hasattr(settings.ingestion, "image_captioner")
        assert "image_captioning.txt" in settings.ingestion.image_captioner.prompt_path

    @pytest.mark.parametrize("scenario, path_exists", [
        ("from_file", True),
        ("fallback_default", False),
    ])
    def test_prompt_loading(self, scenario: str, path_exists: bool):
        """prompt 加载：文件存在用文件，不存在用内置默认"""
        if path_exists:
            captioner = ImageCaptioner(
                _make_settings(),
                prompt_path=str(PROMPT_PATH),
            )
        else:
            captioner = ImageCaptioner(
                _make_settings(),
                prompt_path="/nonexistent/prompt.txt",
            )
        assert "{context}" in captioner.prompt_template


# ============================================================
# Trace（1 个）
# ============================================================

class TestTrace:

    def test_trace_records_stage(self):
        """trace 上下文记录阶段数据"""
        mock_vllm = MockVisionLLM(response="描述")
        settings = _make_settings(vision_enabled=True)
        captioner = ImageCaptioner(settings, vision_llm=mock_vllm)

        img_b64 = base64.b64encode(b"data").decode("ascii")
        chunks = [
            _make_chunk(
                "有图",
                chunk_id="c1",
                image_ids=["img_1"],
                metadata={
                    "image_refs": ["img_1"],
                    "images": [_make_image_dict("img_1", data=img_b64)],
                },
            ),
            _make_chunk("无图", chunk_id="c2"),
        ]
        trace = TraceContext(trace_id="test-captioner")
        captioner.transform(chunks, trace=trace)

        stages = trace.get_stages("image_captioner")
        assert len(stages) == 1
        assert stages[0].data["total"] == 2
        assert stages[0].data["enabled"] is True
        assert stages[0].data["chunks_with_images"] == 1
        assert stages[0].data["chunks_with_captions"] == 1
        assert stages[0].data["chunks_unprocessed"] == 0

