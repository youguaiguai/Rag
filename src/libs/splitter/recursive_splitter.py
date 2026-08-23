"""
RecursiveCharacterTextSplitter 实现 — 纯 Python 递归字符切分器

知识点：
  - 递归字符切分器的工作原理：
    1. 按层级分隔符递归切分：段落(\n\n) → 句子(\n) → 词组( ) → 字符
    2. 优先在高级分隔符处切分，切分后仍超长则用下一级分隔符
    3. 在长度限制内尽量保持语义边界
    4. 对 Markdown 文档天然适配（标题、列表、代码块）
  - 面试考点："为什么要递归？" → 尽量保持语义边界，只在必要时才往更细的粒度切

  - 与 FakeSplitter 的区别：
    - FakeSplitter：按字符位置机械切分，可能切断语义单元
    - RecursiveSplitter：优先在分隔符处切分，保持语义完整性
    - 面试考点："Recursive 的优势？" → 保持语义边界

接口签名：
  RecursiveSplitter(settings: SplitterSettings)
  split_text(text: str) -> list[str]
  provider_name -> str (property)

默认分隔符层级（从粗到细）：
  1. "\n\n" — 段落分隔
  2. "\n"   — 换行/句子分隔
  3. " "    — 词组分隔
  4. ""     — 逐字符（最后兜底）
"""

from __future__ import annotations

from core.settings import SplitterSettings
from libs.splitter.base_splitter import BaseSplitter, SplitterError
from typing import Any


class RecursiveSplitter(BaseSplitter):
    """递归字符切分器 — 按分隔符层级递归切分

    知识点：递归切分算法
      1. 用最粗的分隔符（如 \n\n）切分文本
      2. 如果切分后的片段 <= chunk_size，保留
      3. 如果片段 > chunk_size，用下一级分隔符继续切分
      4. 递归直到所有片段 <= chunk_size 或用完所有分隔符
      5. 合并相邻的小片段，使每个 chunk 尽量接近 chunk_size
      6. 添加 chunk_overlap 重叠，保持上下文连续性

    面试考点："递归切分和定长切分的区别？"
      → 定长按固定位置切，可能切断句子；递归优先在分隔符处切，保持语义
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", " ", ""]

    def __init__(self, settings: SplitterSettings) -> None:
        """初始化 RecursiveSplitter

        接口签名：RecursiveSplitter(settings: SplitterSettings)
        入参：
          - settings: Splitter 配置（包含 chunk_size, chunk_overlap, separators）
        """
        self._provider_name = "recursive"
        self._chunk_size = settings.chunk_size if settings.chunk_size > 0 else 1000
        self._chunk_overlap = settings.chunk_overlap if settings.chunk_overlap >= 0 else 200
        self._separators = settings.separators if settings.separators else self.DEFAULT_SEPARATORS

    def split_text(self, text: str, **kwargs: Any) -> list[str]:
        """递归切分文本

        接口签名：split_text(text: str) -> list[str]
        入参：
          - text: 原始文本
        出参：切分后的文本片段列表
        异常：SplitterError — 切分失败

        处理流程：
          1. 空文本 → 返回空列表
          2. 短文本（<= chunk_size）→ 返回单元素列表
          3. 递归切分：按 separators 层级切分
          4. 合并：将小片段合并到接近 chunk_size
          5. 添加重叠
        """
        if not text:
            return []

        if len(text) <= self._chunk_size:
            return [text]

        # 递归切分
        splits = self._recursive_split(text, self._separators)

        # 合并相邻片段 + 添加重叠
        chunks = self._merge_splits(splits)

        return chunks

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """递归切分：按 separators 层级递归切分

        知识点：递归算法
          - 基础情况：文本 <= chunk_size，直接返回 [text]
          - 递归情况：用当前分隔符切分，对超长片段用下一级分隔符继续切
          - 面试考点："为什么要递归？" → 尽量保持语义边界
        """
        if len(text) <= self._chunk_size:
            return [text]

        if not separators:
            # 所有分隔符都用完了，强制按 chunk_size 切分
            return self._force_split(text)

        sep = separators[0]
        remaining_seps = separators[1:]

        if sep == "":
            # 空分隔符 → 逐字符切分（最后兜底）
            return self._force_split(text)

        # 按当前分隔符切分
        parts = text.split(sep)

        result: list[str] = []
        for part in parts:
            if len(part) <= self._chunk_size:
                if part:  # 忽略空片段
                    result.append(part)
            else:
                # 超长片段用下一级分隔符继续切分
                sub_splits = self._recursive_split(part, remaining_seps)
                result.extend(sub_splits)

        return result

    def _force_split(self, text: str) -> list[str]:
        """强制按 chunk_size 切分（最后的兜底策略）

        知识点：兜底策略
          - 当所有分隔符都无法将文本切到 chunk_size 以内时
          - 直接按字符位置切分
          - 类似 FakeSplitter 的行为
        """
        step = self._chunk_size - self._chunk_overlap
        if step <= 0:
            step = self._chunk_size

        chunks: list[str] = []
        start = 0
        while start < len(text):
            chunk = text[start:start + self._chunk_size]
            chunks.append(chunk)
            start += step
        return chunks

    def _merge_splits(self, splits: list[str]) -> list[str]:
        """合并相邻的小片段，使每个 chunk 尽量接近 chunk_size

        知识点：合并策略
          - 逐个将片段加入当前 chunk
          - 如果加入后超过 chunk_size，开始新 chunk
          - 保留 overlap 重叠（从上一个 chunk 末尾取 overlap 个字符到新 chunk 开头）
          - 面试考点："为什么要合并？" → 避免碎片化，每个 chunk 尽量包含完整信息
        """
        if not splits:
            return []

        chunks: list[str] = []
        current_chunk = splits[0]
        current_sep = ""  # 分隔符，用于合并时恢复格式

        for i in range(1, len(splits)):
            # 尝试加入下一个片段
            # 找到合适的分隔符
            sep = self._find_separator(current_chunk, splits[i])
            candidate = current_chunk + sep + splits[i]

            if len(candidate) <= self._chunk_size:
                # 还能加入，继续合并
                current_chunk = candidate
            else:
                # 超长了，保存当前 chunk，开始新 chunk
                chunks.append(current_chunk)

                # 添加重叠：从当前 chunk 末尾取 overlap 个字符
                if self._chunk_overlap > 0 and len(current_chunk) > self._chunk_overlap:
                    overlap = current_chunk[-self._chunk_overlap:]
                    current_chunk = overlap + sep + splits[i]
                else:
                    current_chunk = splits[i]

        # 保存最后一个 chunk
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _find_separator(self, text1: str, text2: str) -> str:
        """判断两个片段之间应该用什么分隔符

        如果前一个片段以分隔符结尾或后一个片段以分隔符开头，不需要额外分隔符
        否则使用 \n 作为默认分隔符
        """
        if text1.endswith("\n") or text2.startswith("\n"):
            return ""
        if text1.endswith(" ") or text2.startswith(" "):
            return ""
        return "\n"

    @property
    def provider_name(self) -> str:
        """返回切分策略名称"""
        return self._provider_name

