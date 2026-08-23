"""
Azure OpenAI LLM 实现 — 复用 OpenAI LLM 的核心逻辑

知识点：
  - Azure OpenAI 的 API 与 OpenAI 类似，但有以下区别：
    1. endpoint 格式：https://{resource}.openai.azure.com/openai/deployments/{deployment}/chat/completions
    2. 认证方式：api-key header（不是 Bearer token）
    3. 必须指定 api-version 查询参数
  - 面试考点："Azure OpenAI 和 OpenAI 的区别？" → URL 格式 + 认证方式 + api-version

接口签名：
  AzureLLM(settings: LLMSettings)
  chat(messages: list[dict], **kwargs) -> str
  model_name -> str (property)
"""

from __future__ import annotations

from typing import Any

import httpx
from core.settings import LLMSettings
from libs.llm.base_llm import BaseLLM, LLMError, MessageType


class AzureLLM(BaseLLM):
    """Azure OpenAI LLM 实现 — 通过 httpx 调用 Azure OpenAI Chat Completion API

    知识点：Azure OpenAI 的特殊性
      - URL 格式：{azure_endpoint}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}
      - 认证：api-key header（不是 Bearer token）
      - deployment_name：Azure 中的部署名称（与 model 不同）
      - api_version：必须指定（如 "2024-02-15-preview"）
      - 面试考点："Azure 为什么要 deployment_name？" → Azure 中模型按部署管理
    """

    DEFAULT_API_VERSION = "2024-02-15-preview"
    DEFAULT_TIMEOUT = 60.0

    def __init__(self, settings: LLMSettings) -> None:
        """初始化 Azure LLM

        接口签名：AzureLLM(settings: LLMSettings)
        入参：
          - settings: LLM 配置（需要 azure_endpoint, deployment_name, api_key, api_version）
        异常：LLMError — 必要配置缺失
        """
        if not settings.api_key:
            raise LLMError("Azure LLM 初始化失败: api_key 不能为空")
        if not settings.azure_endpoint:
            raise LLMError("Azure LLM 初始化失败: azure_endpoint 不能为空")
        if not settings.deployment_name:
            raise LLMError("Azure LLM 初始化失败: deployment_name 不能为空")

        self._model = settings.model or settings.deployment_name
        self._api_key = settings.api_key
        self._azure_endpoint = settings.azure_endpoint.rstrip("/")
        self._deployment_name = settings.deployment_name
        self._api_version = settings.api_version or self.DEFAULT_API_VERSION
        self._timeout = self.DEFAULT_TIMEOUT

    def chat(self, messages: list[MessageType], **kwargs: Any) -> str:
        """调用 Azure OpenAI Chat Completion API

        接口签名：chat(messages: list[dict], **kwargs) -> str
        入参：
          - messages: 消息列表
          - **kwargs: 可选参数（temperature, max_tokens 等）
        出参：LLM 生成的文本
        异常：LLMError — API 调用失败
        """
        payload: dict[str, Any] = {
            "messages": messages,
        }
        for key in ("temperature", "max_tokens", "top_p", "stop", "stream"):
            if key in kwargs:
                payload[key] = kwargs[key]

        # Azure 认证：api-key header（不是 Bearer）
        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
        }

        # Azure URL 格式
        url = (
            f"{self._azure_endpoint}/openai/deployments/{self._deployment_name}"
            f"/chat/completions?api-version={self._api_version}"
        )

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise LLMError(f"Azure API 请求超时 ({self._timeout}s)")
        except httpx.ConnectError as e:
            raise LLMError(f"Azure API 连接失败: {e}")

        if response.status_code != 200:
            self._raise_http_error(response.status_code, response.text)

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except (KeyError, IndexError) as e:
            raise LLMError(f"Azure API 响应解析失败: {e}")

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model

    def _raise_http_error(self, status_code: int, body: str) -> None:
        """根据 HTTP 状态码抛出对应的 LLMError"""
        if status_code == 401:
            raise LLMError(f"Azure API 认证失败 (401): api_key 无效")
        elif status_code == 429:
            raise LLMError(f"Azure API 速率限制 (429): 请求太频繁")
        elif status_code >= 500:
            raise LLMError(f"Azure API 服务器错误 ({status_code})")
        else:
            raise LLMError(f"Azure API 错误 ({status_code}): {body[:200]}")

