"""
Splitter 工厂与抽象基类的单元测试

知识点：
  - ABC 实例化测试：验证抽象类不能直接实例化
  - 工厂路由测试：验证 provider → 正确的实现类
  - 异常测试：不支持的 provider 应抛出 SplitterError
  - FakeSplitter 测试桩：返回确定性切分结果，不依赖外部库
  - register() 扩展测试：验证开放-封闭原则

测试覆盖：
  1. BaseSplitter 抽象约束 — 不能直接实例化
  2. FakeSplitter 行为 — split_text() 返回切分结果、重叠正确、边界处理
  3. SplitterFactory.create 路由 — provider="fake" → FakeSplitter
  4. SplitterFactory.create 错误 — 不支持的 provider → SplitterError
  5. SplitterFactory.register 扩展 — 注册新 Provider 成功
  6. SplitterFactory.register 校验 — 非 BaseSplitter 子类 → SplitterError
  7. 大小写无关 — provider="Fake" / "FAKE" 都能路由
"""

import pytest

from core.settings import SplitterSettings
from libs.splitter.base_splitter import BaseSplitter, SplitterError
from libs.splitter.splitter_factory import FakeSplitter, SplitterFactory


# ============================================================
# BaseSplitter 抽象约束测试
# ============================================================

class TestBaseSplitterAbstract:
    """验证 BaseSplitter 的抽象约束"""

    def test_cannot_instantiate_base_splitter(self):
        """BaseSplitter 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError, match="abstract method"):
            BaseSplitter()  # type: ignore

    def test_subclass_must_implement_split_text(self):
        """子类必须实现 split_text() 方法"""

        class IncompleteSplitter(BaseSplitter):
            """只实现了 provider_name，没实现 split_text"""
            @property
            def provider_name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteSplitter()  # type: ignore

    def test_subclass_must_implement_provider_name(self):
        """子类必须实现 provider_name 属性"""

        class IncompleteSplitter2(BaseSplitter):
            """只实现了 split_text，没实现 provider_name"""
            def split_text(self, text: str, **kwargs) -> list[str]:
                return [text]

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteSplitter2()  # type: ignore

    def test_complete_subclass_can_instantiate(self):
        """完整实现所有抽象方法的子类可以实例化"""

        class CompleteSplitter(BaseSplitter):
            def split_text(self, text: str, **kwargs) -> list[str]:
                return [text]
            @property
            def provider_name(self) -> str:
                return "complete"

        splitter = CompleteSplitter()
        assert splitter.split_text("hello") == ["hello"]
        assert splitter.provider_name == "complete"


# ============================================================
# FakeSplitter 测试
# ============================================================

class TestFakeSplitter:
    """验证 FakeSplitter 测试桩的行为"""

    def test_split_short_text(self):
        """短文本（<= chunk_size）返回单元素列表"""
        settings = SplitterSettings(provider="fake", chunk_size=100, chunk_overlap=20)
        splitter = FakeSplitter(settings)
        result = splitter.split_text("short text")

        assert len(result) == 1
        assert result[0] == "short text"

    def test_split_long_text(self):
        """长文本被切分为多个 chunk"""
        settings = SplitterSettings(provider="fake", chunk_size=10, chunk_overlap=0)
        splitter = FakeSplitter(settings)
        text = "a" * 25  # 25 字符，每 10 字符切一个 chunk
        result = splitter.split_text(text)

        assert len(result) == 3  # 25 / 10 = 2.5 → 3 个 chunk
        assert result[0] == "a" * 10
        assert result[1] == "a" * 10
        assert result[2] == "a" * 5

    def test_split_with_overlap(self):
        """有重叠时，相邻 chunk 共享部分文本"""
        settings = SplitterSettings(provider="fake", chunk_size=4, chunk_overlap=2)
        splitter = FakeSplitter(settings)
        text = "abcdefghij"  # 10 字符
        result = splitter.split_text(text)

        # step = chunk_size - chunk_overlap = 4 - 2 = 2
        # chunks: [0:4]="abcd", [2:6]="cdef", [4:8]="efgh", [6:10]="ghij", [8:12]="ij"
        assert len(result) == 5
        assert result[0] == "abcd"
        assert result[1] == "cdef"
        assert result[2] == "efgh"
        assert result[3] == "ghij"
        assert result[4] == "ij"

    def test_split_overlap_preserves_context(self):
        """重叠保留上下文连续性 — 相邻 chunk 有公共部分"""
        settings = SplitterSettings(provider="fake", chunk_size=6, chunk_overlap=3)
        splitter = FakeSplitter(settings)
        text = "abcdef"
        result = splitter.split_text(text)

        # step = 6 - 3 = 3
        # chunks: [0:6]="abcdef", [3:6]="def" → 但 start=3, end=9, text[3:9]="def"
        assert len(result) == 2
        assert result[0] == "abcdef"
        assert result[1] == "def"
        # 重叠部分 = "def"（result[0] 的后 3 字符 == result[1] 的前 3 字符）
        assert result[0][-3:] == result[1][:3]

    def test_split_empty_text(self):
        """空字符串返回空列表"""
        settings = SplitterSettings(provider="fake", chunk_size=100, chunk_overlap=20)
        splitter = FakeSplitter(settings)
        result = splitter.split_text("")

        assert result == []

    def test_split_exact_multiple(self):
        """文本长度正好是 chunk_size 的整数倍"""
        settings = SplitterSettings(provider="fake", chunk_size=5, chunk_overlap=0)
        splitter = FakeSplitter(settings)
        text = "a" * 15  # 正好 3 个 chunk
        result = splitter.split_text(text)

        assert len(result) == 3
        assert all(len(chunk) == 5 for chunk in result)

    def test_split_default_chunk_size(self):
        """chunk_size <= 0 时使用默认值 1000"""
        settings = SplitterSettings(provider="fake", chunk_size=0, chunk_overlap=0)
        splitter = FakeSplitter(settings)
        text = "a" * 500  # 小于默认 1000
        result = splitter.split_text(text)

        assert len(result) == 1

    def test_split_default_overlap_when_negative(self):
        """chunk_overlap < 0 时使用默认值 200"""
        settings = SplitterSettings(provider="fake", chunk_size=100, chunk_overlap=-1)
        splitter = FakeSplitter(settings)
        # 内部会修正为 200，step = 100 - 200 = -100 <= 0 → step = 100（无重叠）
        text = "a" * 250
        result = splitter.split_text(text)

        # step 被修正为 chunk_size=100，无重叠切分
        assert len(result) == 3

    def test_split_overlap_larger_than_chunk_size(self):
        """overlap >= chunk_size 时退化为无重叠切分"""
        settings = SplitterSettings(provider="fake", chunk_size=5, chunk_overlap=10)
        splitter = FakeSplitter(settings)
        text = "a" * 15
        result = splitter.split_text(text)

        # step = 5 - 10 = -5 <= 0 → step = 5（无重叠）
        assert len(result) == 3

    def test_provider_name(self):
        """provider_name 返回 'fake'"""
        settings = SplitterSettings(provider="fake")
        splitter = FakeSplitter(settings)
        assert splitter.provider_name == "fake"

    def test_is_base_splitter_instance(self):
        """FakeSplitter 是 BaseSplitter 的实例"""
        settings = SplitterSettings(provider="fake")
        splitter = FakeSplitter(settings)
        assert isinstance(splitter, BaseSplitter)

    def test_split_preserves_text_content(self):
        """切分不丢失文本内容（无重叠时拼接等于原文）"""
        settings = SplitterSettings(provider="fake", chunk_size=10, chunk_overlap=0)
        splitter = FakeSplitter(settings)
        text = "Hello World! This is a test."
        result = splitter.split_text(text)

        # 无重叠时，拼接所有 chunk 应该等于原文
        assert "".join(result) == text

    def test_split_single_char(self):
        """单个字符也能正确切分"""
        settings = SplitterSettings(provider="fake", chunk_size=10, chunk_overlap=0)
        splitter = FakeSplitter(settings)
        result = splitter.split_text("A")

        assert len(result) == 1
        assert result[0] == "A"


# ============================================================
# SplitterFactory 路由测试
# ============================================================

class TestSplitterFactoryRouting:
    """验证 SplitterFactory 的路由逻辑"""

    def test_create_fake_splitter(self):
        """provider='fake' → FakeSplitter"""
        settings = SplitterSettings(provider="fake", chunk_size=100, chunk_overlap=20)
        splitter = SplitterFactory.create(settings)

        assert isinstance(splitter, FakeSplitter)
        assert splitter.provider_name == "fake"

    def test_create_fake_splitter_split_works(self):
        """通过工厂创建的 FakeSplitter 可以正常调用 split_text()"""
        settings = SplitterSettings(provider="fake", chunk_size=10, chunk_overlap=0)
        splitter = SplitterFactory.create(settings)
        result = splitter.split_text("a" * 25)

        assert len(result) == 3
        assert result[0] == "a" * 10

    def test_unsupported_provider_raises_error(self):
        """不支持的 provider → SplitterError"""
        settings = SplitterSettings(provider="nonexistent_provider")
        with pytest.raises(SplitterError, match="不支持的 Splitter provider"):
            SplitterFactory.create(settings)

    def test_unsupported_provider_lists_supported(self):
        """错误信息中列出所有支持的 provider"""
        settings = SplitterSettings(provider="invalid")
        with pytest.raises(SplitterError, match="fake"):
            SplitterFactory.create(settings)

    def test_case_insensitive_provider(self):
        """provider 名称大小写无关"""
        for provider_name in ["fake", "Fake", "FAKE", "FaKe"]:
            settings = SplitterSettings(provider=provider_name, chunk_size=10, chunk_overlap=0)
            splitter = SplitterFactory.create(settings)
            assert isinstance(splitter, FakeSplitter)

    def test_provider_with_whitespace(self):
        """provider 名称前后空格不影响路由"""
        settings = SplitterSettings(provider="  fake  ", chunk_size=10, chunk_overlap=0)
        splitter = SplitterFactory.create(settings)
        assert isinstance(splitter, FakeSplitter)

    def test_empty_provider_raises_error(self):
        """provider 为空字符串 → SplitterError"""
        settings = SplitterSettings(provider="")
        with pytest.raises(SplitterError, match="不支持的 Splitter provider"):
            SplitterFactory.create(settings)


# ============================================================
# SplitterFactory 注册扩展测试
# ============================================================

class TestSplitterFactoryRegister:
    """验证 SplitterFactory.register() 的开放-封闭原则"""

    def test_register_custom_provider(self):
        """注册自定义 Provider 后可以通过工厂创建"""

        class CustomSplitter(BaseSplitter):
            # 知识点：工厂模式要求所有实现类接受 settings 参数
            # SplitterFactory.create() 统一调用 splitter_class(settings)
            def __init__(self, settings: SplitterSettings) -> None:
                self._size = settings.chunk_size or 100

            def split_text(self, text: str, **kwargs) -> list[str]:
                if not text:
                    return []
                return [text[i:i + self._size] for i in range(0, len(text), self._size)]
            @property
            def provider_name(self) -> str:
                return "custom"

        SplitterFactory.register("custom", CustomSplitter)

        try:
            settings = SplitterSettings(provider="custom", chunk_size=5, chunk_overlap=0)
            splitter = SplitterFactory.create(settings)

            assert isinstance(splitter, CustomSplitter)
            assert splitter.provider_name == "custom"
            result = splitter.split_text("abcdefghij")
            assert result == ["abcde", "fghij"]
        finally:
            # 清理：移除注册的 Provider，避免影响其他测试
            SplitterFactory._PROVIDERS.pop("custom", None)

    def test_register_non_base_splitter_raises_error(self):
        """注册非 BaseSplitter 子类 → SplitterError"""

        class NotASplitter:
            def split_text(self):
                return []

        with pytest.raises(SplitterError, match="不是 BaseSplitter 的子类"):
            SplitterFactory.register("bad", NotASplitter)  # type: ignore

    def test_register_overwrite_existing(self):
        """注册同名 Provider 会覆盖原有实现"""

        class AnotherFakeSplitter(BaseSplitter):
            def __init__(self, settings: SplitterSettings) -> None:
                self._size = settings.chunk_size or 100

            def split_text(self, text: str, **kwargs) -> list[str]:
                return [text]  # 总是返回整个文本
            @property
            def provider_name(self) -> str:
                return "another-fake"

        original = SplitterFactory._PROVIDERS.get("fake")

        try:
            SplitterFactory.register("fake", AnotherFakeSplitter)
            settings = SplitterSettings(provider="fake", chunk_size=5, chunk_overlap=0)
            splitter = SplitterFactory.create(settings)

            assert isinstance(splitter, AnotherFakeSplitter)
            assert splitter.split_text("abcdefghij") == ["abcdefghij"]
        finally:
            # 恢复原始 FakeSplitter
            if original is not None:
                SplitterFactory._PROVIDERS["fake"] = original

