"""
list_collections — 列出所有文档集合

接口签名：
  TOOL_SCHEMA: dict — 工具 schema
  list_collections() -> dict — 列出所有集合并返回统计信息
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 数据目录配置
# ============================================================

DATA_DIR = Path("data/documents")


# ============================================================
# 工具 Schema
# ============================================================

TOOL_SCHEMA = {
    "description": "列出所有文档集合及其统计信息。",
    "inputSchema": {
        "type": "object",
        "properties": {},
    },
}


# ============================================================
# 主入口函数
# ============================================================

def list_collections() -> dict[str, Any]:
    """列出所有文档集合

    接口签名：list_collections() -> dict
    入参：无
    出参：MCP 响应字典
      {
        "content": [{"type": "text", "text": "...markdown..."}],
        "structuredContent": {"collections": [{"name": str, "doc_count": int}, ...]}
      }

    处理流程：
      1. 扫描 data/documents/ 子目录
      2. 对每个子目录统计文件数量
      3. 构建 MCP 响应
    """
    collections: list[dict[str, Any]] = []

    if not DATA_DIR.exists() or not DATA_DIR.is_dir():
        # 数据目录不存在，返回空列表
        logger.debug("数据目录不存在: %s", DATA_DIR)
    else:
        # 扫描子目录（集合）
        for item in sorted(DATA_DIR.iterdir()):
            if item.is_dir():
                # 统计文件数量
                doc_count = sum(1 for f in item.rglob("*") if f.is_file())
                collections.append({
                    "name": item.name,
                    "doc_count": doc_count,
                })

    # 构建 Markdown 文本
    if collections:
        lines = ["## 文档集合", ""]
        for i, coll in enumerate(collections, start=1):
            lines.append(f"[{i}] **{coll['name']}** — {coll['doc_count']} 个文件")
        markdown = "\n".join(lines)
    else:
        markdown = (
            "未找到任何文档集合。\n\n**建议**：先运行 "
            "`python scripts/ingest.py --path <文档目录>` 摄取数据。"
        )

    return {
        "content": [{"type": "text", "text": markdown}],
        "structuredContent": {"collections": collections},
    }

