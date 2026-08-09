"""
Embedding 工厂与抽象基类的单元测试

知识点：
  - ABC 实例化测试：验证抽象类不能直接实例化
  - 工厂路由测试：验证 provider → 正确的实现类
  - 异常测试：不支持的 provider 应抛出 EmbeddingError
  - FakeEmbedding 测试桩：返回确定性向量，不依赖真实 API
  - register() 扩展测试：验证开放-封闭原则

测试覆盖：
  1. BaseEmbedding 抽象约束 — 不能直接实例化
  2. FakeEmbedding 行为 — embed() 返回向量、维度正确、确定性
  3. EmbeddingFactory.create 路由 — provider="fake" → FakeEmbedding
  4. EmbeddingFactory.create 错误 — 不支持的 provider → EmbeddingError
  5. EmbeddingFactory.register 扩展 — 注册新 Provider 成功
  6. EmbeddingFactory.register 校验 — 非 BaseEmbedding 子类 → EmbeddingError
  7. 大小写无关 — provider="Fake" / "FAKE" 都能路由
"""

import pytest

from core.settings import EmbeddingSettings
from libs.embedding.base_embedding import BaseEmbedding, EmbeddingError
from libs.embedding.embedding_factory import EmbeddingFactory, FakeEmbedding


# ============================================================
# BaseEmbedding 抽象约束测试
# ============================================================

class TestBaseEmbeddingAbstract:
    """验证 BaseEmbedding 的抽象约束"""

    def test_cannot_instantiate_base_embedding(self):
        """BaseEmbedding 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError, match="abstract method"):
            BaseEmbedding()  # type: ignore

    def test_subclass_must_implement_embed(self):
        """子类必须实现 embed() 方法"""

        class IncompleteEmbedding(BaseEmbedding):
            """只实现了 model_name 和 dimensions，没实现 embed"""
            @property
            def model_name(self) -> str:
                return "incomplete"
            @property
            def dimensions(self) -> int:
                return 128

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteEmbedding()  # type: ignore

    def test_subclass_must_implement_model_name(self):
        """子类必须实现 model_name 属性"""

        class IncompleteEmbedding2(BaseEmbedding):
            """只实现了 embed 和 dimensions，没实现 model_name"""
            def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
                return [[0.0] * 128 for _ in texts]
            @property
            def dimensions(self) -> int:
                return 128

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteEmbedding2()  # type: ignore

    def test_subclass_must_implement_dimensions(self):
        """子类必须实现 dimensions 属性"""

        class IncompleteEmbedding3(BaseEmbedding):
            """只实现了 embed 和 model_name，没实现 dimensions"""
            def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
                return [[0.0] * 128 for _ in texts]
            @property
            def model_name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteEmbedding3()  # type: ignore

    def test_complete_subclass_can_instantiate(self):
        """完整实现所有抽象方法的子类可以实例化"""

        class CompleteEmbedding(BaseEmbedding):
            def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
                return [[0.01] * 10 for _ in texts]
            @property
            def model_name(self) -> str:
                return "complete-model"
            @property
            def dimensions(self) -> int:
                return 10

        emb = CompleteEmbedding()
        assert len(emb.embed(["hello"])) == 1
        assert len(emb.embed(["hello"])[0]) == 10
        assert emb.model_name == "complete-model"
        assert emb.dimensions == 10


# ============================================================
# FakeEmbedding 测试
# ============================================================

class TestFakeEmbedding:
    """验证 FakeEmbedding 测试桩的行为"""

    def test_embed_returns_vectors(self):
        """embed() 返回向量列表"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=128)
        emb = FakeEmbedding(settings)
        vectors = emb.embed(["hello", "world"])

        assert len(vectors) == 2
        assert all(isinstance(v, list) for v in vectors)
        assert all(isinstance(x, float) for v in vectors for x in v)

    def test_embed_vector_dimensions(self):
        """返回的向量维度与 settings.dimensions 一致"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=256)
        emb = FakeEmbedding(settings)
        vectors = emb.embed(["test"])

        assert len(vectors) == 1
        assert len(vectors[0]) == 256

    def test_embed_default_dimensions(self):
        """settings.dimensions <= 0 时使用默认维度 128"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=0)
        emb = FakeEmbedding(settings)
        vectors = emb.embed(["test"])

        assert emb.dimensions == 128
        assert len(vectors[0]) == 128

    def test_embed_deterministic(self):
        """相同文本始终产生相同向量（确定性）"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=64)
        emb = FakeEmbedding(settings)

        v1 = emb.embed(["hello world"])
        v2 = emb.embed(["hello world"])

        assert v1 == v2

    def test_embed_different_texts_different_vectors(self):
        """不同文本产生不同向量"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=64)
        emb = FakeEmbedding(settings)

        v1 = emb.embed(["hello"])
        v2 = emb.embed(["world"])

        assert v1[0] != v2[0]

    def test_embed_empty_list(self):
        """空文本列表返回空向量列表"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=64)
        emb = FakeEmbedding(settings)
        vectors = emb.embed([])

        assert vectors == []

    def test_embed_single_text(self):
        """单个文本返回单个向量"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=32)
        emb = FakeEmbedding(settings)
        vectors = emb.embed(["single text"])

        assert len(vectors) == 1
        assert len(vectors[0]) == 32

    def test_embed_batch_texts(self):
        """批量文本返回对应数量的向量"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=32)
        emb = FakeEmbedding(settings)
        texts = [f"text_{i}" for i in range(100)]
        vectors = emb.embed(texts)

        assert len(vectors) == 100
        assert all(len(v) == 32 for v in vectors)

    def test_embed_values_in_range(self):
        """向量值在 [-1, 1] 范围内（归一化）"""
        settings = EmbeddingSettings(provider="fake", model="fake-model", dimensions=128)
        emb = FakeEmbedding(settings)
        vectors = emb.embed(["test text for range check"])

        assert all(-1.0 <= x <= 1.0 for x in vectors[0])

    def test_model_name_from_settings(self):
        """model_name 来自 settings.model"""
        settings = EmbeddingSettings(provider="fake", model="my-fake-model", dimensions=64)
        emb = FakeEmbedding(settings)
        assert emb.model_name == "my-fake-model"

    def test_model_name_default_when_empty(self):
        """settings.model 为空时使用默认值"""
        settings = EmbeddingSettings(provider="fake", model="", dimensions=64)
        emb = FakeEmbedding(settings)
        assert emb.model_name == "fake-embedding-model"

    def test_dimensions_property(self):
        """dimensions 属性返回正确的维度"""
        settings = EmbeddingSettings(provider="fake", model="fake", dimensions=512)
        emb = FakeEmbedding(settings)
        assert emb.dimensions == 512

    def test_is_base_embedding_instance(self):
        """FakeEmbedding 是 BaseEmbedding 的实例"""
        settings = EmbeddingSettings(provider="fake")
        emb = FakeEmbedding(settings)
        assert isinstance(emb, BaseEmbedding)

    def test_embed_high_dimensions(self):
        """高维度（超过 SHA256 的 32 字节）时正确填充"""
        settings = EmbeddingSettings(provider="fake", model="fake", dimensions=1024)
        emb = FakeEmbedding(settings)
        vectors = emb.embed(["high dimensional text"])

        assert len(vectors[0]) == 1024


# ============================================================
# EmbeddingFactory 路由测试
# ============================================================

class TestEmbeddingFactoryRouting:
    """验证 EmbeddingFactory 的路由逻辑"""

    def test_create_fake_embedding(self):
        """provider='fake' → FakeEmbedding"""
        settings = EmbeddingSettings(provider="fake", model="test-model", dimensions=64)
        emb = EmbeddingFactory.create(settings)

        assert isinstance(emb, FakeEmbedding)
        assert emb.model_name == "test-model"
        assert emb.dimensions == 64

    def test_create_fake_embedding_embed_works(self):
        """通过工厂创建的 FakeEmbedding 可以正常调用 embed()"""
        settings = EmbeddingSettings(provider="fake", model="test-model", dimensions=64)
        emb = EmbeddingFactory.create(settings)
        vectors = emb.embed(["hello", "world"])

        assert len(vectors) == 2
        assert all(len(v) == 64 for v in vectors)

    def test_unsupported_provider_raises_error(self):
        """不支持的 provider → EmbeddingError"""
        settings = EmbeddingSettings(provider="nonexistent_provider")
        with pytest.raises(EmbeddingError, match="不支持的 Embedding provider"):
            EmbeddingFactory.create(settings)

    def test_unsupported_provider_lists_supported(self):
        """错误信息中列出所有支持的 provider"""
        settings = EmbeddingSettings(provider="invalid")
        with pytest.raises(EmbeddingError, match="fake"):
            EmbeddingFactory.create(settings)

    def test_case_insensitive_provider(self):
        """provider 名称大小写无关"""
        for provider_name in ["fake", "Fake", "FAKE", "FaKe"]:
            settings = EmbeddingSettings(provider=provider_name, model="test", dimensions=32)
            emb = EmbeddingFactory.create(settings)
            assert isinstance(emb, FakeEmbedding)

    def test_provider_with_whitespace(self):
        """provider 名称前后空格不影响路由"""
        settings = EmbeddingSettings(provider="  fake  ", model="test", dimensions=32)
        emb = EmbeddingFactory.create(settings)
        assert isinstance(emb, FakeEmbedding)

    def test_empty_provider_raises_error(self):
        """provider 为空字符串 → EmbeddingError"""
        settings = EmbeddingSettings(provider="")
        with pytest.raises(EmbeddingError, match="不支持的 Embedding provider"):
            EmbeddingFactory.create(settings)


# ============================================================
# EmbeddingFactory 注册扩展测试
# ============================================================

class TestEmbeddingFactoryRegister:
    """验证 EmbeddingFactory.register() 的开放-封闭原则"""

    def test_register_custom_provider(self):
        """注册自定义 Provider 后可以通过工厂创建"""

        class CustomEmbedding(BaseEmbedding):
            # 知识点：工厂模式要求所有实现类接受 settings 参数
            # EmbeddingFactory.create() 统一调用 embedding_class(settings)
            def __init__(self, settings: EmbeddingSettings) -> None:
                self._model = settings.model or "custom-model"
                self._dims = settings.dimensions or 64

            def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
                return [[0.0] * self._dims for _ in texts]
            @property
            def model_name(self) -> str:
                return self._model
            @property
            def dimensions(self) -> int:
                return self._dims

        EmbeddingFactory.register("custom", CustomEmbedding)

        try:
            settings = EmbeddingSettings(provider="custom", model="custom-model", dimensions=64)
            emb = EmbeddingFactory.create(settings)

            assert isinstance(emb, CustomEmbedding)
            assert emb.model_name == "custom-model"
            assert emb.dimensions == 64
            assert len(emb.embed(["test"])) == 1
        finally:
            # 清理：移除注册的 Provider，避免影响其他测试
            EmbeddingFactory._PROVIDERS.pop("custom", None)

    def test_register_non_base_embedding_raises_error(self):
        """注册非 BaseEmbedding 子类 → EmbeddingError"""

        class NotAnEmbedding:
            def embed(self):
                return [[0.0]]

        with pytest.raises(EmbeddingError, match="不是 BaseEmbedding 的子类"):
            EmbeddingFactory.register("bad", NotAnEmbedding)  # type: ignore

    def test_register_overwrite_existing(self):
        """注册同名 Provider 会覆盖原有实现"""

        class AnotherFakeEmbedding(BaseEmbedding):
            def __init__(self, settings: EmbeddingSettings) -> None:
                self._model = settings.model or "another-fake"
                self._dims = settings.dimensions or 32

            def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
                return [[0.5] * self._dims for _ in texts]
            @property
            def model_name(self) -> str:
                return self._model
            @property
            def dimensions(self) -> int:
                return self._dims

        original = EmbeddingFactory._PROVIDERS.get("fake")

        try:
            EmbeddingFactory.register("fake", AnotherFakeEmbedding)
            settings = EmbeddingSettings(provider="fake", model="test", dimensions=32)
            emb = EmbeddingFactory.create(settings)

            assert isinstance(emb, AnotherFakeEmbedding)
            vectors = emb.embed(["test"])
            assert vectors[0][0] == 0.5
        finally:
            # 恢复原始 FakeEmbedding
            if original is not None:
                EmbeddingFactory._PROVIDERS["fake"] = original

