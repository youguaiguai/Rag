"""
Vision LLM 抽象基类 — 支持图像输入的多模态 LLM 接口

知识点：
  - Vision LLM vs Text LLM：
    - BaseLLM：只接受文本输入 (messages: list[dict])
    - BaseVisionLLM：接受 文本 + 图像 (text + image_base64)
    - 面试考点："Vision LLM 和普通 LLM 的区别？" → 多了图像理解能力

  - 多模态 API 的图像编码方式：
    1. Base64 编码（本项目采用）：将图片二进制编码为 Base64 字符串
    2. URL 引用：传图片的公开 URL（需要网络可访问）
    - 面试考点："为什么用 Base64 而非 URL？" → 本地文件无公开 URL + Base64 可内联传输

  - Image Captioning 架构：
    1. 读取图片二进制 → Base64 编码
    2. 构造 multimodal prompt（图片 + 文字描述指令）
    3. 调用 Vision LLM → 获取图片描述文本
    4. 将描述文本作为 chunk 的一部分参与检索
    - 面试考点："图片怎么参与 RAG 检索？" → 先 captioning 转文本，再 embed

接口签名：
  BaseVisionLLM.caption_image(image_base64: str, prompt: str) -> str
  BaseVisionLLM.model_name -> str (property)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from libs.llm.base_llm import LLMError
from typing import Any


class BaseVisionLLM(ABC):
    """Vision LLM 抽象基类 — 支持图像输入的多模态 LLM

    知识点：为什么继承 ABC 而非继承 BaseLLM？
      - Vision LLM 的接口与 Text LLM 不同（caption_image vs chat）
      - 接口隔离原则 (ISP)：不应强迫调用方依赖它不需要的方法
      - 面试考点："为什么不继承 BaseLLM？" → 接口不同 + 职责不同

    使用方式：
      vision_llm: BaseVisionLLM = VisionLLMFactory.create(settings)
      description = vision_llm.caption_image(base64_str, "描述这张图片")

    降级策略：
      - Vision LLM 不可用时（未配置/调用失败）→ 跳过图片描述
      - 标记 has_unprocessed_images = true
      - 面试考点："Vision LLM 失败怎么办？" → 降级跳过，不阻断主流程
    """

    @abstractmethod
    def caption_image(self, image_base64: str, prompt: str = "", **kwargs: Any) -> str:
        """根据图片和提示词生成图片描述

        接口签名：caption_image(image_base64: str, prompt: str) -> str
        入参：
          - image_base64: Base64 编码的图片字符串（不含 data:image 前缀）
          - prompt: 图片描述指令（可选，默认使用 image_captioning.txt 模板）
          - **kwargs: 可选参数（temperature, max_tokens 等）
        出参：图片描述文本
        异常：LLMError — API 调用失败 / 图片格式错误 / 超时

        知识点：为什么入参是 Base64 而非文件路径？
          - 解耦：Vision LLM 不关心图片来源（文件/网络/内存）
          - 调用方负责读取文件并编码，Vision LLM 只负责理解
          - 面试考点："为什么传 Base64 而非 path？" → 解耦 + 可测试性

        处理流程（子类实现）：
          1. 构造 multimodal 请求（图片 + 文字）
          2. 调用 Vision API
          3. 返回描述文本
          4. 异常包装为 LLMError
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """返回当前使用的模型名称（用于日志和追踪）

        接口签名：model_name -> str (property)
        示例：'gpt-4o', 'gpt-4-vision'
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """返回 Vision LLM 的 provider 名称

        接口签名：provider_name -> str (property)
        示例：'azure', 'openai', 'fake'
        面试考点："为什么有 model_name 和 provider_name 两个属性？"
          → model_name 是具体模型（gpt-4o），provider_name 是服务提供商（azure）
        """
        ...

