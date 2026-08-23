"""
OpenAI-Compatible LLM 实现 — 支持 OpenAI / Azure / DeepSeek

知识点：
  - OpenAI Chat Completion API：POST /v1/chat/completions
  - 请求格式：{"model": "gpt-4o", "messages": [...], "temperature": 0.7}
  - 响应格式：{"choices": [{"message": {"content": "..."}}]}
  - 使用 httpx 直接调用 REST API（不依赖 openai SDK）
  - 面试考点："为什么不直接用 openai SDK？" → 减少依赖 + 更好的错误控制 + Azure/DeepSeek 兼容

接口签名：
  OpenAILLM(settings: LLMSettings)
  chat(messages: list[dict], **kwargs) -> str
  model_name -> str (property)

OpenAI API 端点：
  - POST https://api.openai.com/v1/chat/completions
  - Headers: Authorization: Bearer <api_key>
  - Body: {"model": "...", "messages": [...], "temperature": ...}

DeepSeek API 端点（OpenAI-Compatible）：
  - POST https://api.deepseek.com/v1/chat/completions
  - 与 OpenAI 格式完全一致，只改 base_url 和 api_key
"""

from __future__ import annotations

from typing import Any

import httpx
from core.settings import LLMSettings
from libs.llm.base_llm import BaseLLM, LLMError, MessageType


class OpenAILLM(BaseLLM):
    """OpenAI LLM 实现 — 通过 httpx 调用 OpenAI Chat Completion API

    知识点：OpenAI-Compatible API
      - OpenAI 的 API 格式已成为行业标准
      - DeepSeek、Azure OpenAI、本地 vLLM 等都兼容此格式
      - 只需改 base_url 和 api_key 即可切换 Provider
      - 面试考点："什么是 OpenAI-Compatible？" → API 格式与 OpenAI 一致，可复用代码

    使用 httpx 而非 openai SDK 的原因：
      1. 减少依赖（openai SDK 体积大，版本更新频繁）
      2. 更好的错误控制（直接处理 HTTP 状态码）
      3. Azure/DeepSeek 都兼容 OpenAI 格式，一个实现覆盖多个 Provider
      4. 面试考点："httpx vs requests？" → httpx 支持同步+异步，类型提示更好
    """

    # OpenAI Chat Completion API 端点
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    CHAT_ENDPOINT = "/chat/completions"
    # 请求超时时间（秒）
    DEFAULT_TIMEOUT = 60.0

    def __init__(self, settings: LLMSettings) -> None:
        """初始化 OpenAI LLM

        接口签名：OpenAILLM(settings: LLMSettings)
        入参：
          - settings: LLM 配置（包含 model、api_key、base_url 等）
        异常：LLMError — api_key 为空
        """
        if not settings.api_key:
            raise LLMError("OpenAI LLM 初始化失败: api_key 不能为空")
        if not settings.model:
            raise LLMError("OpenAI LLM 初始化失败: model 不能为空")

        self._model = settings.model
        self._api_key = settings.api_key
        self._base_url = settings.base_url or self.DEFAULT_BASE_URL
        self._timeout = self.DEFAULT_TIMEOUT

    def chat(self, messages: list[MessageType], **kwargs: Any) -> str:
        """调用 OpenAI Chat Completion API 生成回复

        接口签名：chat(messages: list[dict], **kwargs) -> str
        入参：
          - messages: 消息列表，格式 [{"role": "user", "content": "..."}]
          - **kwargs: 可选参数（temperature, max_tokens 等）
        出参：LLM 生成的文本字符串
        异常：LLMError — API 调用失败

        处理流程：
          1. 构造请求体（model + messages + kwargs）
          2. 发送 HTTP POST 请求
          3. 解析响应 JSON
          4. 返回 choices[0].message.content
          5. 异常包装为 LLMError
        """
        # 构造请求体
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        # 合并可选参数（temperature, max_tokens 等）
        for key in ("temperature", "max_tokens", "top_p", "stop", "stream"):
            if key in kwargs:
                payload[key] = kwargs[key]

        # 构造请求头
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 发送请求
        url = f"{self._base_url}{self.CHAT_ENDPOINT}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise LLMError(f"OpenAI API 请求超时 ({self._timeout}s)")
        except httpx.ConnectError as e:
            raise LLMError(f"OpenAI API 连接失败: {e}")

        # 检查 HTTP 状态码
        if response.status_code != 200:
            self._raise_http_error(response.status_code, response.text)

        # 解析响应
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except (KeyError, IndexError) as e:
            raise LLMError(f"OpenAI API 响应解析失败: {e}")

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model

    def _raise_http_error(self, status_code: int, body: str) -> None:
        """根据 HTTP 状态码抛出对应的 LLMError

        知识点：HTTP 状态码映射
          - 401: 认证失败（api_key 错误）
          - 429: 速率限制（请求太频繁）
          - 500: 服务器内部错误
          - 其他: 通用错误
        """
        if status_code == 401:
            raise LLMError(f"OpenAI API 认证失败 (401): api_key 无效")
        elif status_code == 429:
            raise LLMError(f"OpenAI API 速率限制 (429): 请求太频繁")
        elif status_code >= 500:
            raise LLMError(f"OpenAI API 服务器错误 ({status_code})")
        else:
            raise LLMError(f"OpenAI API 错误 ({status_code}): {body[:200]}")

