"""
文件完整性检查 — SHA256 哈希追踪

知识点：SHA256 在增量摄取中的作用
  - 判断文件是否变更：新哈希 ≠ 旧哈希 → 内容变了，需要重新处理
  - 增量摄取：跳过未变更文件，避免重复处理
  - 幂等性保证：相同文件内容产生相同哈希
  - 面试考点："为什么要做文件完整性检查？" → 增量摄取 + 幂等性

  - 持久化设计：
    - 使用 JSON 文件存储 {source_path: file_hash} 映射
    - 路径：data/db/file_hashes.json（与 Chroma 同级目录）
    - 面试考点："为什么用 JSON 而非 SQLite？" → 简单 + 单文件 + 无依赖

  - 增量摄取流程：
    1. 读取文件二进制 → 计算 SHA256
    2. 查询已存储的哈希
    3. 哈希相同 → 跳过（文件未变更）
    4. 哈希不同或不存在 → 需要处理
    5. 处理完成后 → 更新哈希记录
    - 面试考点："增量摄取怎么实现的？" → SHA256 前后对比

接口签名：
  FileIntegrityChecker(db_path: str)
  compute_hash(file_path: str) -> str
  has_changed(file_path: str) -> bool
  update_hash(file_path: str) -> None
  get_hash(file_path: str) -> str | None
  save() -> None
  load() -> None
  remove(file_path: str) -> bool
  clear() -> None
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class FileIntegrityError(Exception):
    """文件完整性检查异常

    知识点：自定义异常
      - 文件读取失败 / 哈希存储读写失败时抛出
      - 面试考点："什么时候抛 FileIntegrityError？" → 文件不存在 / IO 错误
    """
    pass


class FileIntegrityChecker:
    """文件完整性检查器 — 基于 SHA256 的增量摄取

    知识点：增量摄取的核心逻辑
      1. 首次运行：所有文件都是新的 → 全量处理 → 存储哈希
      2. 第二次运行：比较哈希 → 只处理变更文件 → 更新哈希
      3. 幂等性：重复运行不会产生重复数据

    持久化设计：
      - JSON 文件：{source_path: file_hash} 映射
      - load() 在初始化时自动调用
      - save() 在更新哈希后手动调用（或由 Pipeline 编排调用）
      - 面试考点："为什么 JSON 而非 SQLite？" → 简单 + 无依赖 + 量小

    SHA256 原理：
      - 输入任意长度的数据 → 输出固定 64 字符的十六进制字符串
      - 雪崩效应：输入 1 bit 变化 → 输出完全不同
      - 不可逆：无法从哈希反推原文
      - 面试考点："SHA256 的特点？" → 固定长度 + 雪崩效应 + 不可逆
    """

    DEFAULT_DB_PATH = "data/db/file_hashes.json"

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        """初始化文件完整性检查器

        接口签名：FileIntegrityChecker(db_path: str)
        入参：
          - db_path: 哈希存储文件路径（JSON 格式）
        """
        self._db_path = Path(db_path)
        self._hashes: dict[str, str] = {}
        self.load()

    def compute_hash(self, file_path: str) -> str:
        """计算文件的 SHA256 哈希

        接口签名：compute_hash(file_path: str) -> str
        入参：file_path — 文件路径
        出参：64 字符的十六进制 SHA256 哈希
        异常：FileIntegrityError — 文件不存在或读取失败

        知识点：分块读取
          - 不一次性 read() 整个文件（大文件可能 OOM）
          - 按 8KB 块循环读取，逐块更新哈希
          - 面试考点："为什么不一次读全部？" → 大文件 OOM 风险
        """
        path = Path(file_path)
        if not path.exists():
            raise FileIntegrityError(f"文件不存在: {file_path}")

        sha256 = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(8192)  # 8KB 块
                    if not chunk:
                        break
                    sha256.update(chunk)
        except IOError as e:
            raise FileIntegrityError(f"读取文件失败: {file_path}: {e}")

        return sha256.hexdigest()

    def has_changed(self, file_path: str) -> bool:
        """检查文件是否已变更（哈希不同或首次出现）

        接口签名：has_changed(file_path: str) -> bool
        入参：file_path — 文件路径
        出参：
          - True: 文件已变更或首次出现（需要处理）
          - False: 文件未变更（可跳过）

        知识点：增量判断逻辑
          - 新文件（不在哈希表中）→ True（需要处理）
          - 哈希相同 → False（跳过）
          - 哈希不同 → True（需要重新处理）
          - 面试考点："has_changed 的逻辑？" → 新文件 True + 哈希不同 True + 哈希相同 False
        """
        current_hash = self.compute_hash(file_path)
        stored_hash = self._hashes.get(file_path)

        if stored_hash is None:
            return True  # 首次出现
        return current_hash != stored_hash

    def update_hash(self, file_path: str) -> str:
        """更新文件的哈希记录

        接口签名：update_hash(file_path: str) -> str
        入参：file_path — 文件路径
        出参：当前文件的 SHA256 哈希
        异常：FileIntegrityError — 文件读取失败

        知识点：更新策略
          - 计算当前哈希 → 存入内存字典
          - 不自动 save()（由 Pipeline 批量保存，减少 IO）
          - 面试考点："为什么不自动 save？" → 批量操作减少 IO
        """
        current_hash = self.compute_hash(file_path)
        self._hashes[file_path] = current_hash
        return current_hash

    def get_hash(self, file_path: str) -> str | None:
        """获取已存储的文件哈希

        接口签名：get_hash(file_path: str) -> str | None
        出参：已存储的哈希字符串，未记录则返回 None
        """
        return self._hashes.get(file_path)

    def save(self) -> None:
        """将哈希记录持久化到 JSON 文件

        接口签名：save() -> None
        异常：FileIntegrityError — 写入失败

        知识点：持久化设计
          - 自动创建父目录
          - JSON 格式可读性好
          - 原子写入：先写临时文件再 rename（简单实现直接写）
        """
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump(self._hashes, f, ensure_ascii=False, indent=2)
        except IOError as e:
            raise FileIntegrityError(f"保存哈希记录失败: {e}")

    def load(self) -> None:
        """从 JSON 文件加载哈希记录

        接口签名：load() -> None

        知识点：容错加载
          - 文件不存在 → 空字典（首次运行）
          - JSON 解析失败 → 空字典（文件损坏，不阻断流程）
          - 面试考点："load 失败怎么办？" → 容错降级为空字典
        """
        if not self._db_path.exists():
            self._hashes = {}
            return

        try:
            with open(self._db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._hashes = {str(k): str(v) for k, v in data.items()}
            else:
                self._hashes = {}
        except (json.JSONDecodeError, IOError):
            self._hashes = {}

    def remove(self, file_path: str) -> bool:
        """删除文件的哈希记录

        接口签名：remove(file_path: str) -> bool
        出参：True 如果记录存在并被删除，False 如果记录不存在

        知识点：清理策略
          - DocumentManager 删除文档时同步清理哈希记录
          - 保持存储一致性
        """
        if file_path in self._hashes:
            del self._hashes[file_path]
            return True
        return False

    def clear(self) -> None:
        """清空所有哈希记录

        接口签名：clear() -> None

        用途：--force 全量重新摄取时清空旧记录
        """
        self._hashes.clear()

    def get_all_paths(self) -> list[str]:
        """获取所有已记录的文件路径

        接口签名：get_all_paths() -> list[str]
        出参：已记录文件路径列表

        用途：DocumentManager 列出所有文档 / 数据浏览器
        """
        return list(self._hashes.keys())

    @property
    def db_path(self) -> str:
        """返回哈希存储文件路径"""
        return str(self._db_path)

    @property
    def count(self) -> int:
        """返回已记录的文件数量"""
        return len(self._hashes)

