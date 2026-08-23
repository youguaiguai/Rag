"""B7.5: Recursive Splitter 测试

测试结构：
  1. 初始化测试（4 个）
  2. 基本切分测试（8 个）
  3. Markdown 结构保持测试（4 个）
  4. 工厂路由测试（2 个）
"""

from __future__ import annotations

import pytest
from core.settings import SplitterSettings
from libs.splitter.base_splitter import BaseSplitter, SplitterError
from libs.splitter.recursive_splitter import RecursiveSplitter
from libs.splitter.splitter_factory import SplitterFactory


class TestRecursiveSplitterInit:

    def test_is_base_splitter(self):
        s = RecursiveSplitter(SplitterSettings(provider="recursive"))
        assert isinstance(s, BaseSplitter)

    def test_provider_name(self):
        s = RecursiveSplitter(SplitterSettings(provider="recursive"))
        assert s.provider_name == "recursive"

    def test_default_chunk_size(self):
        s = RecursiveSplitter(SplitterSettings(provider="recursive"))
        assert s._chunk_size == 1000

    def test_custom_chunk_size(self):
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=500, chunk_overlap=50))
        assert s._chunk_size == 500
        assert s._chunk_overlap == 50


class TestRecursiveSplitterBasic:

    def test_empty_text(self):
        """空文本 → 空列表"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive"))
        assert s.split_text("") == []

    def test_short_text(self):
        """短文本（<= chunk_size）→ 单元素列表"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0))
        result = s.split_text("这是一段短文本。")
        assert len(result) == 1
        assert result[0] == "这是一段短文本。"

    def test_split_by_paragraph(self):
        """按段落分隔符切分"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=20, chunk_overlap=0))
        text = "第一段落内容比较长\n\n第二段落内容也比较长\n\n第三段落内容同样长"
        result = s.split_text(text)
        assert len(result) >= 2
        # 每个段落应该被保留
        assert "第一段落" in result[0]

    def test_long_paragraph_recursive(self):
        """超长段落用下一级分隔符继续切"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=15, chunk_overlap=0))
        # 一个没有换行符的长段落
        text = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ"
        result = s.split_text(text)
        assert len(result) >= 2
        # 每个 chunk 不应超过 chunk_size + overlap 太多
        for chunk in result:
            assert len(chunk) <= 20  # 允许一点余量

    def test_chunk_size_respected(self):
        """切分后的片段大致不超过 chunk_size"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=50, chunk_overlap=0))
        text = "\n\n".join([f"这是第{i}段内容，有一些文字。" for i in range(20)])
        result = s.split_text(text)
        for chunk in result:
            # 允许少量超出（合并时可能略超）
            assert len(chunk) <= 100

    def test_overlap_preserved(self):
        """有 overlap 时，相邻 chunk 有重叠内容"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=20, chunk_overlap=5))
        text = "abcdefghij" * 10  # 100 字符
        result = s.split_text(text)
        if len(result) >= 2:
            # 第二个 chunk 的开头应该和第一个 chunk 的结尾有重叠
            overlap = result[0][-5:]
            assert result[1].startswith(overlap) or overlap in result[1]

    def test_preserves_newline_structure(self):
        """切分不会破坏换行结构"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0))
        text = "标题\n\n正文第一段\n\n正文第二段"
        result = s.split_text(text)
        assert len(result) == 1  # 短文本不分
        assert "标题" in result[0]
        assert "正文第一段" in result[0]

    def test_deterministic(self):
        """同一文本多次切分结果相同"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=30, chunk_overlap=5))
        text = "这是第一段。\n\n这是第二段。\n\n这是第三段。\n\n这是第四段。"
        r1 = s.split_text(text)
        r2 = s.split_text(text)
        assert r1 == r2


class TestRecursiveSplitterMarkdown:

    def test_markdown_headers_not_broken(self):
        """Markdown 标题不被切断"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0))
        text = "# 标题一\n\n正文内容\n\n## 子标题\n\n更多内容"
        result = s.split_text(text)
        # 标题应该完整保留在某个 chunk 中
        all_text = "".join(result)
        assert "# 标题一" in all_text
        assert "## 子标题" in all_text

    def test_code_block_structure(self):
        """代码块结构基本保持"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0))
        text = "一些说明文字\n\n```python\nprint('hello')\nprint('world')\n```\n\n更多说明"
        result = s.split_text(text)
        all_text = "".join(result)
        assert "```" in all_text
        assert "print('hello')" in all_text

    def test_multiple_paragraphs(self):
        """多段落正确切分"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=30, chunk_overlap=0))
        text = "\n\n".join([f"段落{i}的内容" for i in range(10)])
        result = s.split_text(text)
        assert len(result) >= 2
        # 所有段落内容都在结果中
        all_text = "".join(result)
        for i in range(10):
            assert f"段落{i}" in all_text

    def test_list_structure(self):
        """列表项结构保持"""
        s = RecursiveSplitter(SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0))
        text = "- 项目一\n- 项目二\n- 项目三\n- 项目四"
        result = s.split_text(text)
        all_text = "".join(result)
        assert "- 项目一" in all_text
        assert "- 项目四" in all_text


class TestRecursiveSplitterFactory:

    def test_factory_creates_recursive(self):
        """provider=recursive → RecursiveSplitter"""
        settings = SplitterSettings(provider="recursive", chunk_size=500, chunk_overlap=50)
        s = SplitterFactory.create(settings)
        assert isinstance(s, RecursiveSplitter)
        assert s.provider_name == "recursive"

    def test_factory_recursive_with_custom_separators(self):
        """provider=recursive + 自定义分隔符"""
        settings = SplitterSettings(
            provider="recursive",
            chunk_size=200,
            separators=["\n\n", "\n", "。", "，", " "],
        )
        s = SplitterFactory.create(settings)
        assert isinstance(s, RecursiveSplitter)
        result = s.split_text("第一句。第二句。第三句。第四句。第五句。")
        assert len(result) >= 1

