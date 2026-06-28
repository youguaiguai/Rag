#!/usr/bin/env python3
"""
Smart Knowledge Hub — MCP Server 启动入口

知识点：
  - MCP (Model Context Protocol): Anthropic 定义的 AI 工具调用协议
  - Stdio Transport: 通过 stdin/stdout 通信，日志必须走 stderr
  - main.py 是整个系统的入口点，负责：
    1. 加载配置 (A3 实现)
    2. 初始化 MCP Server (E1 阶段实现)
    3. 启动 Stdio Transport 通信循环 (E1 阶段实现)
  - Fail-Fast 原则：启动时校验配置，缺失直接退出
"""

import sys
from pathlib import Path

# 将 src/ 加入 sys.path，使直接运行 main.py 时也能找到 core/ 和 observability/ 模块
# 知识点：pyproject.toml 的 pythonpath = ["src"] 只对 pytest 生效
#         直接 python main.py 时需要手动添加
_src_dir = str(Path(__file__).parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from core.settings import SettingsError, load_settings
from observability.logger import get_logger


def main() -> None:
    """MCP Server 主入口函数

    处理流程：
      1. 初始化日志
      2. 加载配置（load_settings → 读取YAML → 校验必填字段）
      3. 校验失败 → fail-fast 退出
      4. 后续：初始化 MCP Server、启动通信循环（E1 实现）

    知识点：
      - MCP Stdio Transport 约束：stdout 只能输出 JSON-RPC 消息
      - 所有日志、调试信息必须输出到 stderr
      - 面试考点："MCP Server 启动时做了什么？" → 加载配置 → 校验 → 初始化
    """
    logger = get_logger("rag.main")

    try:
        logger.info("正在加载配置...")
        settings = load_settings()
        logger.info(f"配置加载成功: LLM={settings.llm.provider}/{settings.llm.model}, "
                     f"Embedding={settings.embedding.provider}/{settings.embedding.model}")
    except SettingsError as e:
        # Fail-Fast：配置错误直接退出，不继续运行
        logger.error(f"配置加载失败: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)

    logger.info("Smart Knowledge Hub MCP Server 配置加载完成")
    logger.info("NOTE: Full MCP Server implementation will be added in Stage E")


if __name__ == "__main__":
    main()
