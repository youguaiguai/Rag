"""
配置加载与校验的单元测试

知识点：
  - pytest fixture：用 tmp_path 创建临时配置文件，测试完自动清理
  - 参数化测试：@pytest.mark.parametrize 一个测试函数覆盖多种场景
  - 异常测试：pytest.raises 上下文管理器捕获期望的异常
  - 测试分层：本文件是 unit test，不依赖真实 config/settings.yaml

测试覆盖：
  1. 正常加载 — 完整配置 → Settings 对象字段正确
  2. 环境变量替换 — ${VAR} → os.environ 值
  3. 缺失文件 — 不存在的路径 → SettingsError
  4. 空/无效 YAML — 格式错误 → SettingsError
  5. 必填字段缺失 — 删除 llm.provider → SettingsError 包含字段路径
  6. 条件校验 — vision_llm.enabled=true 但缺 provider → SettingsError
  7. validate_settings 单独测试 — 不依赖 load_settings
"""

import os
import pytest
from pathlib import Path

from core.settings import (
    Settings,
    SettingsError,
    LLMSettings,
    EmbeddingSettings,
    VisionLLMSettings,
    RerankSettings,
    load_settings,
    validate_settings,
)


# ============================================================
# 辅助函数：生成最小可用的 YAML 配置
# ============================================================

def _minimal_yaml(**overrides) -> str:
    """生成最小可用的配置 YAML 字符串

    知识点：为什么不用真实 config/settings.yaml？
      - 单元测试应自包含，不依赖外部文件
      - 用函数生成配置，方便局部修改（如删除某个字段）
      - 面试考点："测试配置加载时为什么不用真实配置？" → 隔离性 + 可控性
    """
    config = {
        "llm": {"provider": "openai", "model": "gpt-4o"},
        "embedding": {"provider": "openai", "model": "text-embedding-3-small", "dimensions": 1536},
        "vision_llm": {"enabled": False},
    }
    # 应用覆盖
    for key, value in overrides.items():
        if "." in key:
            # 支持嵌套覆盖，如 "llm.provider": "ollama"
            parts = key.split(".", 1)
            if parts[0] not in config:
                config[parts[0]] = {}
            if isinstance(config.get(parts[0]), dict):
                config[parts[0]][parts[1]] = value
        else:
            config[key] = value

    import yaml
    return yaml.dump(config, default_flow_style=False)


def _write_config(tmp_path: Path, content: str, filename: str = "settings.yaml") -> Path:
    """将 YAML 内容写入临时文件并返回路径"""
    config_file = tmp_path / filename
    config_file.write_text(content, encoding="utf-8")
    return config_file


# ============================================================
# 测试用例
# ============================================================

class TestLoadSettingsSuccess:
    """正常加载测试"""

    def test_load_minimal_config(self, tmp_path: Path):
        """最小配置加载成功"""
        config_file = _write_config(tmp_path, _minimal_yaml())
        settings = load_settings(str(config_file))

        assert isinstance(settings, Settings)
        assert settings.llm.provider == "openai"
        assert settings.llm.model == "gpt-4o"
        assert settings.embedding.provider == "openai"
        assert settings.embedding.model == "text-embedding-3-small"
        assert settings.embedding.dimensions == 1536

    def test_load_full_config(self, tmp_path: Path):
        """完整配置加载成功，包含所有字段"""
        import yaml
        full_config = {
            "llm": {"provider": "azure", "model": "gpt-4o", "azure_endpoint": "https://example.openai.azure.com",
                     "deployment_name": "gpt-4o", "api_version": "2024-02-15-preview"},
            "embedding": {"provider": "openai", "model": "text-embedding-3-small", "dimensions": 1536},
            "vision_llm": {"enabled": False},
            "vector_store": {"backend": "chroma", "persist_path": "./data/db/chroma"},
            "retrieval": {"sparse_backend": "bm25", "fusion_algorithm": "rrf",
                          "top_k_dense": 20, "top_k_sparse": 20, "top_k_final": 10},
            "rerank": {"enabled": False, "backend": "cross_encoder", "model": "test-model", "top_m": 30},
            "observability": {"enabled": True, "log_level": "DEBUG", "detail_level": "verbose"},
            "dashboard": {"enabled": True, "port": 8501},
        }
        config_file = _write_config(tmp_path, yaml.dump(full_config, default_flow_style=False))
        settings = load_settings(str(config_file))

        assert settings.llm.provider == "azure"
        assert settings.llm.azure_endpoint == "https://example.openai.azure.com"
        assert settings.vector_store.backend == "chroma"
        assert settings.retrieval.top_k_final == 10
        assert settings.rerank.enabled is False
        assert settings.observability.log_level == "DEBUG"

    def test_default_values_for_missing_sections(self, tmp_path: Path):
        """YAML 中缺少某个 section 时，使用 dataclass 默认值"""
        config_file = _write_config(tmp_path, _minimal_yaml())
        settings = load_settings(str(config_file))

        # vector_store 在 minimal yaml 中未定义，应使用默认值
        assert settings.vector_store.backend == "chroma"
        assert settings.vector_store.persist_path == "./data/db/chroma"

        # retrieval 使用默认值
        assert settings.retrieval.fusion_algorithm == "rrf"
        assert settings.retrieval.top_k_final == 10

    def test_extra_fields_ignored(self, tmp_path: Path):
        """YAML 中有 dataclass 未定义的字段时，不影响加载"""
        import yaml
        config = yaml.safe_load(_minimal_yaml())
        config["llm"]["unknown_field"] = "should_be_ignored"  # type: ignore
        config_file = _write_config(tmp_path, yaml.dump(config))
        settings = load_settings(str(config_file))

        assert settings.llm.provider == "openai"


class TestLoadSettingsEnvVars:
    """环境变量替换测试"""

    def test_env_var_substitution(self, tmp_path: Path):
        """${VAR} 格式的环境变量被正确替换"""
        os.environ["TEST_RAG_API_KEY"] = "sk-test-12345"

        import yaml
        config = yaml.safe_load(_minimal_yaml())
        config["llm"]["api_key"] = "${TEST_RAG_API_KEY}"
        config_file = _write_config(tmp_path, yaml.dump(config))

        settings = load_settings(str(config_file))
        assert settings.llm.api_key == "sk-test-12345"

        # 清理
        del os.environ["TEST_RAG_API_KEY"]

    def test_env_var_missing_returns_empty(self, tmp_path: Path):
        """环境变量不存在时，替换为空字符串"""
        import yaml
        config = yaml.safe_load(_minimal_yaml())
        config["llm"]["api_key"] = "${NONEXISTENT_VAR_XYZ}"
        config_file = _write_config(tmp_path, yaml.dump(config))

        settings = load_settings(str(config_file))
        assert settings.llm.api_key == ""

    def test_env_var_in_string(self, tmp_path: Path):
        """${VAR} 嵌入在字符串中间时也能替换"""
        os.environ["TEST_RAG_HOST"] = "localhost"

        import yaml
        config = yaml.safe_load(_minimal_yaml())
        config["llm"]["base_url"] = "http://${TEST_RAG_HOST}:11434"
        config_file = _write_config(tmp_path, yaml.dump(config))

        settings = load_settings(str(config_file))
        assert settings.llm.base_url == "http://localhost:11434"

        del os.environ["TEST_RAG_HOST"]


class TestLoadSettingsErrors:
    """错误场景测试"""

    def test_file_not_found(self):
        """配置文件不存在时抛出 SettingsError"""
        with pytest.raises(SettingsError, match="配置文件不存在"):
            load_settings("/nonexistent/path/settings.yaml")

    def test_empty_yaml(self, tmp_path: Path):
        """空 YAML 文件（解析为 None）抛出 SettingsError"""
        config_file = _write_config(tmp_path, "")
        with pytest.raises(SettingsError, match="配置文件格式错误"):
            load_settings(str(config_file))

    def test_invalid_yaml_syntax(self, tmp_path: Path):
        """YAML 语法错误时抛出 SettingsError"""
        config_file = _write_config(tmp_path, "llm:\n  provider: openai\n  model: [invalid")
        with pytest.raises(SettingsError, match="YAML 解析失败"):
            load_settings(str(config_file))

    def test_yaml_is_list_not_dict(self, tmp_path: Path):
        """YAML 内容是列表而非字典时抛出 SettingsError"""
        config_file = _write_config(tmp_path, "- item1\n- item2")
        with pytest.raises(SettingsError, match="配置文件格式错误"):
            load_settings(str(config_file))


class TestValidateSettings:
    """validate_settings 校验测试

    知识点：为什么单独测 validate_settings？
      - 分离加载和校验，可以单独测校验逻辑
      - 不需要创建临时文件，直接构造 Settings 对象
      - 面试考点："如何测试校验逻辑？" → 直接构造 dataclass，不需要文件 IO
    """

    def test_valid_settings(self):
        """合法 Settings 校验通过"""
        settings = Settings(
            llm=LLMSettings(provider="openai", model="gpt-4o"),
            embedding=EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536),
            vision_llm=VisionLLMSettings(enabled=False),
        )
        # 不应抛出异常
        validate_settings(settings)

    def test_missing_llm_provider(self):
        """缺失 llm.provider → SettingsError 包含 'llm.provider'"""
        settings = Settings(
            llm=LLMSettings(provider="", model="gpt-4o"),
            embedding=EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536),
        )
        with pytest.raises(SettingsError, match="llm.provider"):
            validate_settings(settings)

    def test_missing_llm_model(self):
        """缺失 llm.model → SettingsError 包含 'llm.model'"""
        settings = Settings(
            llm=LLMSettings(provider="openai", model=""),
            embedding=EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536),
        )
        with pytest.raises(SettingsError, match="llm.model"):
            validate_settings(settings)

    def test_missing_embedding_provider(self):
        """缺失 embedding.provider → SettingsError 包含 'embedding.provider'"""
        settings = Settings(
            llm=LLMSettings(provider="openai", model="gpt-4o"),
            embedding=EmbeddingSettings(provider="", model="text-embedding-3-small", dimensions=1536),
        )
        with pytest.raises(SettingsError, match="embedding.provider"):
            validate_settings(settings)

    def test_missing_embedding_model(self):
        """缺失 embedding.model → SettingsError"""
        settings = Settings(
            llm=LLMSettings(provider="openai", model="gpt-4o"),
            embedding=EmbeddingSettings(provider="openai", model="", dimensions=1536),
        )
        with pytest.raises(SettingsError, match="embedding.model"):
            validate_settings(settings)

    def test_invalid_embedding_dimensions(self):
        """embedding.dimensions <= 0 → SettingsError"""
        settings = Settings(
            llm=LLMSettings(provider="openai", model="gpt-4o"),
            embedding=EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=0),
        )
        with pytest.raises(SettingsError, match="embedding.dimensions"):
            validate_settings(settings)

    def test_vision_llm_enabled_but_missing_provider(self):
        """vision_llm.enabled=true 但缺 provider → SettingsError"""
        settings = Settings(
            llm=LLMSettings(provider="openai", model="gpt-4o"),
            embedding=EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536),
            vision_llm=VisionLLMSettings(enabled=True, provider="", model=""),
        )
        with pytest.raises(SettingsError, match="vision_llm.provider"):
            validate_settings(settings)

    def test_rerank_enabled_but_missing_backend(self):
        """rerank.enabled=true 但缺 backend → SettingsError"""
        settings = Settings(
            llm=LLMSettings(provider="openai", model="gpt-4o"),
            embedding=EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536),
            rerank=RerankSettings(enabled=True, backend=""),
        )
        with pytest.raises(SettingsError, match="rerank.backend"):
            validate_settings(settings)

    def test_multiple_missing_fields(self):
        """多个必填字段同时缺失 → SettingsError 包含所有缺失字段"""
        settings = Settings(
            llm=LLMSettings(provider="", model=""),
            embedding=EmbeddingSettings(provider="", model=""),
        )
        with pytest.raises(SettingsError, match="llm.provider.*llm.model.*embedding.provider.*embedding.model"):
            validate_settings(settings)

    def test_default_settings_fails_validation(self):
        """默认 Settings（所有字段为空）校验失败"""
        settings = Settings()
        with pytest.raises(SettingsError):
            validate_settings(settings)


class TestLoadSettingsMissingFields:
    """通过 YAML 文件测试缺失必填字段"""

    def test_missing_llm_provider_in_yaml(self, tmp_path: Path):
        """YAML 中 llm.provider 为空 → SettingsError"""
        import yaml
        config = yaml.safe_load(_minimal_yaml())
        config["llm"]["provider"] = ""
        config_file = _write_config(tmp_path, yaml.dump(config))

        with pytest.raises(SettingsError, match="llm.provider"):
            load_settings(str(config_file))

    def test_missing_llm_section_in_yaml(self, tmp_path: Path):
        """YAML 中完全缺少 llm section → SettingsError"""
        import yaml
        config = yaml.safe_load(_minimal_yaml())
        del config["llm"]
        config_file = _write_config(tmp_path, yaml.dump(config))

        with pytest.raises(SettingsError, match="llm.provider"):
            load_settings(str(config_file))

    def test_missing_embedding_section_in_yaml(self, tmp_path: Path):
        """YAML 中完全缺少 embedding section → SettingsError"""
        import yaml
        config = yaml.safe_load(_minimal_yaml())
        del config["embedding"]
        config_file = _write_config(tmp_path, yaml.dump(config))

        with pytest.raises(SettingsError, match="embedding.provider"):
            load_settings(str(config_file))
