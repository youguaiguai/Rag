"""
LLM 抽象基类 — 可插拔架构的核心

知识点：
  - ABC (Abstract Base Class)：Python 标准库提供的抽象基类机制
  - @abstractmethod：标记抽象方法，子类必须实现，否则实例化时抛出 TypeError
  - 可插拔架构：上层代码只依赖 BaseLLM 接口，不关心底层用的是哪个 Provider
  - 工厂模式配合：LLMFactory.create(settings) 根据 provider 字段创建具体实现

关键接口签名（面试必须掌握）：
  BaseLLM.chat(messages: list[dict], **kwargs) -> str
    入参：
      - messages: 消息列表，格式 [{"role": "system"/"user"/"assistant", "content": "..."}]
      - **kwargs: 可选参数（temperature, max_tokens 等），传递给底层 API
    出参：LLM 生成的文本字符串
    异常：子类实现中可能抛出 LLMError

  BaseLLM.model_name -> str
    属性：返回当前使用的模型名称（用于日志和追踪）

设计原则：
  - 接口最小化：只暴露 chat() 一个核心方法，避免过度设计
  - 统一入参出参：所有 Provider 用相同的 messages 格式和返回值类型
  - 异常统一：子类应将 Provider 特有的异常转换为 LLMError
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# ============================================================
# 自定义异常
# ============================================================

class LLMError(Exception):
    """LLM 调用异常

    知识点：为什么自定义异常？
      - 统一不同 Provider 的异常类型（OpenAI APIConnectionError、
        Azure AuthenticationError 等都转换为 LLMError）
      - 上层代码只需 except LLMError，不需要关心底层 Provider
      - 面试考点："异常转译模式" — 将底层异常包装为领域异常
    """
    pass


# ============================================================
# 消息类型定义
# ============================================================

# 消息格式：[{"role": "system"/"user"/"assistant", "content": "..."}]
# 知识点：这是 OpenAI Chat Completion API 的标准格式
#   - system: 系统提示词，定义 AI 的角色和行为
#   - user: 用户输入
#   - assistant: AI 的回复（用于多轮对话上下文）
#   - 其他 Provider（Azure/Ollama/DeepSeek）也兼容此格式
MessageType = dict[str, str]


# ============================================================
# BaseLLM 抽象基类
# ============================================================

class BaseLLM(ABC):
    """LLM 抽象基类 — 所有 LLM 实现的统一接口

    接口签名：
      chat(messages: list[dict], **kwargs) -> str
      model_name -> str (property)

    使用方式（上层代码不关心具体 Provider）：
      llm: BaseLLM = LLMFactory.create(settings)
      response = llm.chat([
          {"role": "system", "content": "你是 RAG 助手"},
          {"role": "user", "content": "什么是向量数据库？"}
      ])

    知识点：为什么用 ABC 而不是普通继承？
      - ABC + @abstractmethod 强制子类实现 chat()，忘记实现会 TypeError
      - 普通继承没有这个约束，运行时才发现漏实现
      - 面试考点："ABC 的作用？" → 编译期约束 + 类型安全 + 接口契约
    """

    @abstractmethod
    def chat(self, messages: list[MessageType], **kwargs: Any) -> str:
        """调用 LLM 生成回复

        接口签名：chat(messages: list[dict], **kwargs) -> str
        入参：
          - messages: 消息列表，格式 [{"role": "...", "content": "..."}]
          - **kwargs: 可选参数（temperature, max_tokens, stop 等）
        出参：LLM 生成的文本字符串
        异常：LLMError — API 调用失败 / 超时 / 认证错误

        知识点：为什么返回 str 而不是自定义 Response 对象？
          - A3 阶段保持接口最小化，str 满足当前需求
          - 后续可扩展为 LLMResponse（包含 usage、finish_reason 等元数据）
          - 面试考点："接口设计的 YAGNI 原则" — 不要提前设计不需要的功能
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """返回当前使用的模型名称（用于日志和追踪）

        接口签名：model_name -> str (property)
        示例：'gpt-4o', 'deepseek-chat', 'llama3'
        """
        ...
