#!/usr/bin/env python3
"""
Dashboard 启动脚本

知识点：Dashboard 启动
  - streamlit run 启动 Streamlit 应用
  --server.port 指定端口（默认 8501）
  --server.headless true 无头模式（服务器部署用）
  --browser.gatherUsageStats false 禁用遥测

启动命令：
  python scripts/start_dashboard.py
  python scripts/start_dashboard.py --port 8502

面试考点：
  - "Dashboard 有什么用途？" → 可观测性 + 调试 + 运维监控
  - "为什么要单独启动脚本？" → 封装 streamlit 参数 + 环境检查
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """启动 Streamlit Dashboard"""
    project_root = Path(__file__).parent.parent
    app_path = project_root / "src" / "observability" / "dashboard" / "app.py"

    if not app_path.exists():
        print(f"❌ Dashboard 入口文件不存在: {app_path}")
        sys.exit(1)

    print("=" * 50)
    print("  Modular RAG Dashboard")
    print("=" * 50)
    print(f"  App: {app_path}")
    print(f"  URL: http://localhost:8501")
    print("=" * 50)

    try:
        subprocess.run(
            [
                sys.executable, "-m", "streamlit", "run",
                str(app_path),
                "--server.port", "8501",
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false",
            ],
            cwd=str(project_root),
            check=True,
        )
    except KeyboardInterrupt:
        print("\nDashboard 已停止")
    except subprocess.CalledProcessError as e:
        print(f"Dashboard 启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

