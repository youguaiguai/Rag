"""
Azure Vision LLM 实现 — 通过 Azure OpenAI GPT-4o Vision API 生成图片描述

知识点：
  - Azure OpenAI Vision API：
    - 与普通 Chat Completion API 使用相同端点
    - 区别：messages 中的 content 可以包含 image_url 类型
    - 请求格式：{"messages": [{"role": "user", "content": [
        {"type": "text", "text": "描述这张图片"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
      ]}]}
    - 面试考点："Vision API 和普通 API 的区别？" → content 从 string 变成 list[dict]

  - Base64 图片编码：
    - 原始图片二进制 → base64.b64encode() → 字符串
    - 拼接 data URI 前缀：data:image/{format};base64,{base64_str}
    - 面试考点："为什么要加 data URI 前缀？" → API 需要识别图片格式

  - 降级模式：
    - Vision LLM 调用失败时（未配置/超时/认证失败）→ 返回空字符串
    - 由调用方（ImageCaptioner）决定是否跳过或标记 has_unprocessed_images
    - 面试考点："Vision 失败为什么返回空字符串而非抛异常？" → 不阻断摄取流程

接口签名：
  AzureVisionLLM(settings: VisionLLMSettings)
  caption_image(image_base64: str, prompt: str) -> str
  model_name -> str (property)
  provider_name -> str (property)
"""

from __future__ import annotations

import httpx
from core.settings import VisionLLMSettings
from libs.llm.base_llm import LLMError
from libs.llm.base_vision_llm import BaseVisionLLM
from typing import Any


class AzureVisionLLM(BaseVisionLLM):
    """Azure OpenAI Vision LLM 实现 — GPT-4o / GPT-4-Vision

    知识点：Azure Vision API 调用流程
      1. 构造 multimodal content（text + image_url）
      2. POST 到 Azure OpenAI deployment 端点
      3. 解析 choices[0].message.content 获取描述
      4. 异常包装为 LLMError

    与 AzureLLM 的区别：
      - AzureLLM: messages.content 是 string
      - AzureVisionLLM: messages.content 是 list[dict]（多模态格式）
      - 面试考点："为什么 content 从 string 变成 list？" → 需要同时传文本和图片

    使用 httpx 而非 openai SDK 的原因：
      - 与 OpenAILLM/AzureLLM 保持一致
      - 减少 openai SDK 依赖
      - 更好的错误控制
    """

    DEFAULT_API_VERSION = "2024-02-15-preview"
    DEFAULT_TIMEOUT = 120.0  # Vision 推理可能比纯文本慢

    def __init__(self, settings: VisionLLMSettings) -> None:
        """初始化 Azure Vision LLM

        接口签名：AzureVisionLLM(settings: VisionLLMSettings)
        入参：
          - settings: Vision LLM 配置（需要 azure_endpoint, deployment_name, api_key）
        异常：LLMError — 必要配置缺失
        """
        if not settings.api_key:
            raise LLMError("Azure Vision LLM 初始化失败: api_key 不能为空")
        if not settings.azure_endpoint:
            raise LLMError("Azure Vision LLM 初始化失败: azure_endpoint 不能为空")
        if not settings.deployment_name:
            raise LLMError("Azure Vision LLM 初始化失败: deployment_name 不能为空")

        self._model = settings.model or settings.deployment_name
        self._api_key = settings.api_key
        self._azure_endpoint = settings.azure_endpoint.rstrip("/")
        self._deployment_name = settings.deployment_name
        self._api_version = settings.api_version or self.DEFAULT_API_VERSION
        self._timeout = self.DEFAULT_TIMEOUT

    def caption_image(self, image_base64: str, prompt: str = "", **kwargs: Any) -> str:
        """调用 Azure OpenAI Vision API 生成图片描述

        接口签名：caption_image(image_base64: str, prompt: str) -> str
        入参：
          - image_base64: Base64 编码的图片字符串（不含 data URI 前缀）
          - prompt: 图片描述指令
        出参：图片描述文本
        异常：LLMError — API 调用失败

        处理流程：
          1. 构造 data URI（拼接 image/png 前缀）
          2. 构造 multimodal messages（text + image_url）
          3. POST 到 Azure OpenAI
          4. 解析 choices[0].message.content
          5. 异常包装为 LLMError
        """
        if not image_base64:
            raise LLMError("Azure Vision LLM: image_base64 不能为空")

        # 构造 data URI（默认 png 格式）
        data_uri = f"data:image/png;base64,{image_base64}"

        # 构造 multimodal content
        text_content = prompt or "请描述这张图片的内容。"
        content: list[dict[str, Any]] = [
            {"type": "text", "text": text_content},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]

        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": content}],
        }
        # 合并可选参数
        for key in ("temperature", "max_tokens", "top_p", "stop"):
            if key in kwargs:
                payload[key] = kwargs[key]

        # Azure 认证：api-key header
        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
        }

        # Azure URL 格式（与 AzureLLM 相同）
        url = (
            f"{self._azure_endpoint}/openai/deployments/{self._deployment_name}"
            f"/chat/completions?api-version={self._api_version}"
        )

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise LLMError(f"Azure Vision API 请求超时 ({self._timeout}s)")
        except httpx.ConnectError as e:
            raise LLMError(f"Azure Vision API 连接失败: {e}")

        # 检查 HTTP 状态码
        if response.status_code != 200:
            self._raise_http_error(response.status_code, response.text)

        # 解析响应
        try:
            data = response.json()
            content_str = data["choices"][0]["message"]["content"]
            return content_str
        except (KeyError, IndexError) as e:
            raise LLMError(f"Azure Vision API 响应解析失败: {e}")

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model

    @property
    def provider_name(self) -> str:
        """返回 provider 名称"""
        return "azure"

    def _raise_http_error(self, status_code: int, body: str) -> None:
        """根据 HTTP 状态码抛出对应的 LLMError

        知识点：Vision API 特有的错误
          - 400: 图片格式不支持 / Base64 编码错误
          - 401: 认证失败
          - 429: 速率限制
          - 500+: 服务器错误
        """
        if status_code == 400:
            raise LLMError(f"Azure Vision API 错误 (400): 请求无效（可能是图片格式错误）")
        elif status_code == 401:
            raise LLMError(f"Azure Vision API 认证失败 (401): api_key 无效")
        elif status_code == 429:
            raise LLMError(f"Azure Vision API 速率限制 (429): 请求太频繁")
        elif status_code >= 500:
            raise LLMError(f"Azure Vision API 服务器错误 ({status_code})")
        else:
            raise LLMError(f"Azure Vision API 错误 ({status_code}): {body[:200]}")

