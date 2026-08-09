"""
配置加载与校验模块 — Settings 模式

知识点：
  - dataclass：Python 标准库，自动生成 __init__、__repr__、__eq__
  - Settings 模式：用 dataclass 树集中管理所有配置，取代散落的 dict
  - Fail-Fast 原则：启动时校验必填字段，缺失直接报错退出
  - 环境变量替换：${VAR} 格式，运行时从 os.environ 读取，API Key 不写死

关键接口签名（面试必须掌握）：
  load_settings(path: str = "config/settings.yaml") -> Settings
    入参：YAML 配置文件路径
    出参：Settings 对象（包含所有配置的 dataclass 树）
    异常：SettingsError — 配置文件不存在 / 字段缺失 / 类型错误

  validate_settings(settings: Settings) -> None
    入参：Settings 对象
    出参：None（校验通过）或抛出 SettingsError
    核心逻辑：检查必填字段，错误信息包含字段路径如 "embedding.provider"

设计原则：
  - Settings 只做"结构与最小校验"，不做任何网络/IO 的"业务初始化"
  - 校验与加载分离：load_settings 负责读取+解析，validate_settings 负责校验
  - 这样测试时可以单独测校验逻辑，不需要真实配置文件
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import yaml


# ============================================================
# 自定义异常
# ============================================================

class SettingsError(Exception):
    """配置错误异常

    知识点：自定义异常的设计
      - 继承 Exception，让调用方可以用 except SettingsError 精确捕获
      - 错误信息包含字段路径（如 "embedding.provider"），方便定位
      - 面试考点："为什么自定义异常而不是用 ValueError？" → 精确捕获 + 语义清晰
    """
    pass


# ============================================================
# 子配置 dataclass
# ============================================================
# 知识点：为什么拆成多个小 dataclass 而不是一个大类？
#   - 单一职责：每个子配置类只管自己的字段
#   - 类型安全：LLMSettings.provider 是 str，不是 Any
#   - IDE 补全：settings.llm.provider 有补全，settings["llm"]["provider"] 没有

@dataclass
class LLMSettings:
    """LLM 配置

    接口签名：LLMSettings(provider: str, model: str, api_key: str = "", ...)
    关键字段：
      - provider: 必填，决定用哪个 LLM 实现（openai/azure/ollama/deepseek）
      - model: 必填，模型名称
      - api_key: 可选，运行时从环境变量注入
    """
    provider: str = ""
    model: str = ""
    api_key: str = ""
    # Azure 专用
    azure_endpoint: str = ""
    deployment_name: str = ""
    api_version: str = ""
    # Ollama 专用
    base_url: str = ""


@dataclass
class EmbeddingSettings:
    """Embedding 配置

    接口签名：EmbeddingSettings(provider: str, model: str, dimensions: int = 1536, ...)
    关键字段：
      - dimensions: 向量维度，必须与模型匹配（如 text-embedding-3-small = 1536）
    """
    provider: str = ""
    model: str = ""
    dimensions: int = 1536
    api_key: str = ""
    # Azure 专用
    azure_endpoint: str = ""
    deployment_name: str = ""
    api_version: str = ""
    # Ollama 专用
    base_url: str = ""


@dataclass
class VisionLLMSettings:
    """Vision LLM 配置（图片描述生成）

    接口签名：VisionLLMSettings(enabled: bool, provider: str, model: str, ...)
    关键字段：
      - enabled: 是否启用图片描述功能
    """
    enabled: bool = True
    provider: str = ""
    model: str = ""
    api_key: str = ""
    azure_endpoint: str = ""
    deployment_name: str = ""
    base_url: str = ""


@dataclass
class SplitterSettings:
    """Splitter 配置（文本切分策略）

    接口签名：SplitterSettings(provider: str, chunk_size: int, chunk_overlap: int, separators: list[str])
    关键字段：
      - provider: 切分策略类型（recursive/semantic/fixed/fake）
      - chunk_size: 每个 Chunk 的最大字符数
      - chunk_overlap: 相邻 Chunk 之间的重叠字符数（保留上下文连续性）
    """
    provider: str = "recursive"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    separators: List[str] = field(default_factory=lambda: ["\n\n", "\n", " ", ""])


@dataclass
class VectorStoreSettings:
    """向量存储配置

    接口签名：VectorStoreSettings(backend: str, persist_path: str, ...)
    关键字段：
      - backend: 向量数据库后端（chroma/qdrant/pinecone）
      - persist_path: 持久化存储路径
    """
    backend: str = "chroma"
    persist_path: str = "./data/db/chroma"


@dataclass
class RetrievalSettings:
    """检索配置

    接口签名：RetrievalSettings(sparse_backend: str, fusion_algorithm: str,
                                  top_k_dense: int, top_k_sparse: int, top_k_final: int)
    关键字段：
      - fusion_algorithm: 融合算法（rrf/weighted_sum）
      - top_k_dense/top_k_sparse: 各路召回数量
      - top_k_final: 最终返回数量
    """
    sparse_backend: str = "bm25"
    fusion_algorithm: str = "rrf"
    top_k_dense: int = 20
    top_k_sparse: int = 20
    top_k_final: int = 10


@dataclass
class RerankSettings:
    """重排配置

    接口签名：RerankSettings(enabled: bool, backend: str, model: str, top_m: int)
    关键字段：
      - enabled: 是否启用重排
      - backend: 重排后端（none/cross_encoder/llm）
      - top_m: 送入重排的候选数量
    """
    enabled: bool = False
    backend: str = "cross_encoder"
    model: str = ""
    top_m: int = 30


@dataclass
class EvaluationSettings:
    """评估配置

    接口签名：EvaluationSettings(backends: List[str], golden_test_set: str)
    关键字段：
      - backends: 评估后端列表（如 [ragas, custom]）
      - golden_test_set: 黄金测试集文件路径
    """
    backends: List[str] = field(default_factory=lambda: ["ragas"])
    golden_test_set: str = "./tests/fixtures/golden_test_set.json"


@dataclass
class ObservabilitySettings:
    """可观测性配置

    接口签名：ObservabilitySettings(enabled: bool, log_file: str, log_level: str, detail_level: str)
    """
    enabled: bool = True
    log_file: str = "./logs/traces.jsonl"
    log_level: str = "INFO"
    detail_level: str = "standard"


@dataclass
class DashboardSettings:
    """Dashboard 管理平台配置

    接口签名：DashboardSettings(enabled: bool, port: int, traces_dir: str,
                                  auto_refresh: bool, refresh_interval: int)
    """
    enabled: bool = True
    port: int = 8501
    traces_dir: str = "./logs"
    auto_refresh: bool = True
    refresh_interval: int = 5


# ============================================================
# 顶层 Settings — 聚合所有子配置
# ============================================================

@dataclass
class Settings:
    """项目总配置 — 聚合所有子配置的 dataclass 树

    接口签名：Settings(llm: LLMSettings, embedding: EmbeddingSettings, ...)

    数据流：
      config/settings.yaml → yaml.safe_load() → dict → Settings dataclass 树

    面试考点：
      "Settings 对象长什么样？"
      → settings.llm.provider          # "openai"
      → settings.embedding.model       # "text-embedding-3-small"
      → settings.retrieval.top_k_final # 10
      → settings.rerank.enabled        # False
    """
    llm: LLMSettings = field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)
    vision_llm: VisionLLMSettings = field(default_factory=VisionLLMSettings)
    splitter: SplitterSettings = field(default_factory=SplitterSettings)
    vector_store: VectorStoreSettings = field(default_factory=VectorStoreSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    rerank: RerankSettings = field(default_factory=RerankSettings)
    evaluation: EvaluationSettings = field(default_factory=EvaluationSettings)
    observability: ObservabilitySettings = field(default_factory=ObservabilitySettings)
    dashboard: DashboardSettings = field(default_factory=DashboardSettings)


# ============================================================
# 配置加载与校验
# ============================================================

def _resolve_env_vars(value: Any) -> Any:
    """替换字符串中的 ${VAR} 环境变量引用

    接口签名：_resolve_env_vars(value: Any) -> Any
    入参：任意值（只有 str 类型会处理）
    出参：替换环境变量后的值
    示例：'${OPENAI_API_KEY}' → os.environ['OPENAI_API_KEY']

    知识点：环境变量替换的两种常见格式
      - ${VAR}：Bash 风格，本项目采用
      - ${VAR:-default}：带默认值，更安全但本项目暂不实现
    """
    if not isinstance(value, str):
        return value

    # 正则匹配 ${VAR_NAME} 格式
    pattern = re.compile(r'\$\{(\w+)\}')

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name, "")
        if not env_value:
            # 环境变量未设置时返回空字符串（不报错，因为测试环境可能没配 API Key）
            return ""
        return env_value

    return pattern.sub(_replace, value)


def _resolve_env_vars_recursive(data: Any) -> Any:
    """递归替换 dict 中所有字符串值的环境变量

    接口签名：_resolve_env_vars_recursive(data: Any) -> Any
    入参：YAML 解析后的 dict/list/str/int
    出参：环境变量替换后的 dict/list/str/int
    """
    if isinstance(data, dict):
        return {k: _resolve_env_vars_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_env_vars_recursive(item) for item in data]
    elif isinstance(data, str):
        return _resolve_env_vars(data)
    return data


def _dict_to_dataclass(cls: type, data: dict) -> Any:
    """将 dict 递归转换为 dataclass 实例

    接口签名：_dict_to_dataclass(cls: type, data: dict) -> Any
    入参：
      - cls: 目标 dataclass 类（如 LLMSettings）
      - data: YAML 解析出的 dict（如 {"provider": "openai", "model": "gpt-4o"}）
    出参：cls 的实例

    知识点：为什么需要这个函数？
      - yaml.safe_load() 返回的是 dict，不是 dataclass
      - 必须手动转换，Python 没有内置的 dict→dataclass 自动映射
      - 递归处理嵌套的 dataclass（如 Settings 包含 LLMSettings）

    技术细节：
      - 只取 dataclass 中定义的字段，忽略 YAML 中多余的字段（向前兼容）
      - 字段类型是 dataclass 时递归转换
      - 使用类型映射表解决 from __future__ annotations 导致的字符串类型问题

    Bug 修复记录：
      - 初版用 f.type 检查是否是 dataclass，但因为 from __future__ annotations
        f.type 变成了字符串（如 "LLMSettings"）而非实际类型
      - 修复方案：用 _FIELD_TYPE_MAP 显式映射字段名到 dataclass 类型
    """
    if not isinstance(data, dict):
        return cls()

    from dataclasses import fields as dc_fields

    kwargs = {}
    for f in dc_fields(cls):
        if f.name not in data:
            continue

        value = data[f.name]
        field_type = _FIELD_TYPE_MAP.get((cls.__name__, f.name))

        if field_type is not None and isinstance(value, dict):
            # 递归转换嵌套的 dataclass
            kwargs[f.name] = _dict_to_dataclass(field_type, value)
        else:
            kwargs[f.name] = value

    return cls(**kwargs)


# 字段名到 dataclass 类型的映射表
# 解决 from __future__ annotations 导致 f.type 为字符串的问题
# 格式：(类名, 字段名) → dataclass 类型
_FIELD_TYPE_MAP: dict[tuple[str, str], type] = {
    ("Settings", "llm"): LLMSettings,
    ("Settings", "embedding"): EmbeddingSettings,
    ("Settings", "vision_llm"): VisionLLMSettings,
    ("Settings", "vector_store"): VectorStoreSettings,
    ("Settings", "retrieval"): RetrievalSettings,
    ("Settings", "rerank"): RerankSettings,
    ("Settings", "evaluation"): EvaluationSettings,
    ("Settings", "observability"): ObservabilitySettings,
    ("Settings", "splitter"): SplitterSettings,
    ("Settings", "dashboard"): DashboardSettings,
}


def load_settings(path: str = "config/settings.yaml") -> Settings:
    """加载配置文件并返回 Settings 对象

    接口签名：load_settings(path: str = "config/settings.yaml") -> Settings
    入参：YAML 配置文件路径（默认 config/settings.yaml）
    出参：Settings 对象（包含所有配置的 dataclass 树）
    异常：SettingsError — 文件不存在 / YAML 解析失败 / 字段校验失败

    处理流程：
      1. 读取 YAML 文件
      2. yaml.safe_load() 解析为 dict
      3. 递归替换 ${VAR} 环境变量
      4. dict → Settings dataclass 树
      5. validate_settings() 校验必填字段
      6. 返回 Settings 对象

    面试考点：
      "配置加载的完整流程？" → 读文件 → 解析 → 替换环境变量 → 转dataclass → 校验
    """
    config_path = Path(path)

    # 1. 检查文件存在
    if not config_path.exists():
        raise SettingsError(f"配置文件不存在: {config_path}")

    # 2. 读取并解析 YAML
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SettingsError(f"YAML 解析失败: {config_path}: {e}")
    except Exception as e:
        raise SettingsError(f"读取配置文件失败: {config_path}: {e}")

    if not isinstance(raw_data, dict):
        raise SettingsError(f"配置文件格式错误: 期望 dict，得到 {type(raw_data).__name__}")

    # 3. 替换环境变量
    resolved_data = _resolve_env_vars_recursive(raw_data)

    # 4. dict → Settings dataclass
    settings = _dict_to_dataclass(Settings, resolved_data)

    # 5. 校验必填字段
    validate_settings(settings)

    return settings


def validate_settings(settings: Settings) -> None:
    """校验 Settings 必填字段

    接口签名：validate_settings(settings: Settings) -> None
    入参：Settings 对象
    出参：None（校验通过）
    异常：SettingsError — 必填字段缺失，错误信息包含字段路径

    校验逻辑：
      - llm.provider: 必填，决定使用哪个 LLM 实现
      - llm.model: 必填，模型名称
      - embedding.provider: 必填，决定使用哪个 Embedding 实现
      - embedding.model: 必填，模型名称
      - embedding.dimensions: 必须 > 0，向量维度

    面试考点：
      "validate_settings 校验了什么？" → 必填字段存在 + 值合法
      "为什么不在 dataclass __post_init__ 中校验？" → 分离加载和校验，测试更灵活
    """
    errors: List[str] = []

    # ---- LLM 必填校验 ----
    if not settings.llm.provider:
        errors.append("llm.provider")
    if not settings.llm.model:
        errors.append("llm.model")

    # ---- Embedding 必填校验 ----
    if not settings.embedding.provider:
        errors.append("embedding.provider")
    if not settings.embedding.model:
        errors.append("embedding.model")
    if settings.embedding.dimensions <= 0:
        errors.append("embedding.dimensions (必须 > 0)")

    # ---- Vision LLM 条件校验 ----
    if settings.vision_llm.enabled:
        if not settings.vision_llm.provider:
            errors.append("vision_llm.provider (当 vision_llm.enabled=true 时必填)")
        if not settings.vision_llm.model:
            errors.append("vision_llm.model (当 vision_llm.enabled=true 时必填)")

    # ---- Rerank 条件校验 ----
    if settings.rerank.enabled:
        if not settings.rerank.backend:
            errors.append("rerank.backend (当 rerank.enabled=true 时必填)")

    # 汇总错误
    if errors:
        missing = ", ".join(errors)
        raise SettingsError(f"配置校验失败，缺失或无效字段: {missing}")
