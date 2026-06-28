# LLM 抽象基类
# 知识点：BaseLLM 是可插拔架构的核心
#   - chat(messages) -> str: 统一的对话接口
#   - 不同 Provider（Azure/OpenAI/Ollama/DeepSeek）只需实现此接口
#   - 上层代码不关心底层用的是哪个 LLM，只调用 chat()
