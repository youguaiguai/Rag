"""
Ollama LLM 实现 — 本地模型 HTTP API

知识点：
  - Ollama 是什么：本地运行的 LLM 服务，支持 llama3、qwen 等开源模型
  - API 端点：POST {base_url}/api/chat
  - 请求格式：{"model": "llama3", "messages": [...], "stream": false}
  - 响应格式：{"message": {"content": "..."}, "done": true}
  - 与 OpenAI API 的区别：URL 路径不同 / 响应结构不同
  - 面试考点："Ollama 和 OpenAI 的区别？" → 本地运行 + API 格式不同

接口签名：
  OllamaLLM(settings: LLMSettings)
  chat(messages: list[dict], **kwargs) -> str
  model_name -> str (property)

Ollama API 端点：
  - POST http://localhost:11434/api/chat
  - Body: {"model": "llama3", "messages": [...], "stream": false}
  - Response: {"message": {"role": "assistant", "content": "..."}, "done": true}
"""

from __future__ import annotations

from typing import Any

import httpx
from core.settings import LLMSettings
from libs.llm.base_llm import BaseLLM, LLMError, MessageType


class OllamaLLM(BaseLLM):
    """Ollama LLM 实现 — 通过 httpx 调用 Ollama HTTP API

    知识点：Ollama API 特点
      - 本地部署，默认端口 11434
      - 支持 stream 模式（本项目用 stream=false 简化处理）
      - 响应格式与 OpenAI 不同：{"message": {"content": "..."}} vs {"choices": [{"message": {...}}]}
      - 面试考点："Ollama 为什么不用 Bearer token？" → 本地服务，无需认证

    错误处理：
      - 连接失败：Ollama 服务未启动
      - 超时：模型推理慢（本地模型可能比 API 慢）
      - 404：模型未下载
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    CHAT_ENDPOINT = "/api/chat"
    DEFAULT_TIMEOUT = 120.0  # 本地模型推理可能较慢

    def __init__(self, settings: LLMSettings) -> None:
        """初始化 Ollama LLM

        接口签名：OllamaLLM(settings: LLMSettings)
        入参：
          - settings: LLM 配置（需要 model，base_url 可选默认 localhost:11434）
        异常：LLMError — model 为空
        """
        if not settings.model:
            raise LLMError("Ollama LLM 初始化失败: model 不能为空")

        self._model = settings.model
        self._base_url = settings.base_url or self.DEFAULT_BASE_URL
        self._timeout = self.DEFAULT_TIMEOUT

    def chat(self, messages: list[MessageType], **kwargs: Any) -> str:
        """调用 Ollama /api/chat 生成回复

        接口签名：chat(messages: list[dict], **kwargs) -> str
        入参：
          - messages: 消息列表
          - **kwargs: 可选参数（temperature, top_p 等）
        出参：LLM 生成的文本
        异常：LLMError — API 调用失败 / 连接失败 / 超时

        处理流程：
          1. 构造请求体（model + messages + stream=false）
          2. 发送 HTTP POST 请求
          3. 解析响应 JSON
          4. 返回 message.content
          5. 异常包装为 LLMError（不泄露敏感配置）
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,  # 非流式模式，一次返回完整结果
        }
        # 合并可选参数
        for key in ("temperature", "top_p", "top_k", "num_predict"):
            if key in kwargs:
                payload[key] = kwargs[key]

        headers = {"Content-Type": "application/json"}
        url = f"{self._base_url}{self.CHAT_ENDPOINT}"

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise LLMError(f"Ollama API 请求超时 ({self._timeout}s)")
        except httpx.ConnectError as e:
            raise LLMError(
                f"Ollama API 连接失败: 无法连接到 {self._base_url}。"
                f"请确认 Ollama 服务已启动。"
            )

        if response.status_code != 200:
            self._raise_http_error(response.status_code, response.text)

        try:
            data = response.json()
            content = data["message"]["content"]
            return content
        except (KeyError, IndexError) as e:
            raise LLMError(f"Ollama API 响应解析失败: {e}")

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self._model

    def _raise_http_error(self, status_code: int, body: str) -> None:
        """根据 HTTP 状态码抛出对应的 LLMError

        知识点：错误信息不泄露敏感配置
          - 只报告状态码和简短描述
          - 不暴露 base_url、api_key 等
          - 面试考点："错误处理的安全性？" → 不泄露敏感信息
        """
        if status_code == 404:
            raise LLMError(f"Ollama API 错误 (404): 模型 '{self._model}' 未找到，请先 ollama pull {self._model}")
        elif status_code == 400:
            raise LLMError(f"Ollama API 错误 (400): 请求参数无效")
        elif status_code >= 500:
            raise LLMError(f"Ollama API 服务器错误 ({status_code})")
        else:
            raise LLMError(f"Ollama API 错误 ({status_code})")

