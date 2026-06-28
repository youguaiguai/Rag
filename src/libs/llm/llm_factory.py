# LLM 工厂 — 根据配置创建对应的 LLM 实例
# 知识点：工厂模式 (Factory Pattern)
#   - 核心思想：将"创建哪个实现"的决策从业务代码中解耦
#   - LLMFactory.create(settings) -> BaseLLM
#   - settings.llm.provider = "azure" → 返回 AzureLLM
#   - settings.llm.provider = "openai" → 返回 OpenAILLM
#   - 好处：切换 Provider 只改配置，不改代码
