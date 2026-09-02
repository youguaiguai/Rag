"""
MetadataEnricher — Chunk 元数据增强（title/summary/tags）

知识点：Transform 链的第二个组件
  - 职责：为每个 chunk 生成语义元数据（title、summary、tags）
  - 规则模式：基于文本统计提取（首行/关键词/前N字），零成本、确定性
  - LLM 模式：调用 LLM 生成语义丰富的元数据（理解全文后提取）
  - 降级：LLM 失败 → 回退到规则结果，不阻塞 ingestion

元数据用途（面试考点）：
  - title: 向用户展示 chunk 主题，用于检索结果卡片
  - summary: 摘要用于结果预览，减少用户阅读成本
  - tags: 用于过滤、聚类、相关推荐

两阶段策略（与 ChunkRefiner 一致）：
  1. 规则阶段（确定性兜底）：首行/标题提取 + 前N字摘要 + 关键词频率提取
  2. LLM 阶段（可选增强）：语义理解后生成更准确的 title/summary/tags
  - 顺序：规则先执行，LLM 成功覆盖规则结果，失败保留规则结果

接口签名：
  MetadataEnricher(settings: Settings, llm: BaseLLM | None = None, prompt_path: str | None = None)
  transform(chunks: list[Chunk], trace: TraceContext | None = None) -> list[Chunk]
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from ingestion.transform.base_transform import BaseTransform
from libs.llm.base_llm import BaseLLM, LLMError
from libs.llm.llm_factory import LLMFactory
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from core.types import Chunk

logger = logging.getLogger(__name__)


# ============================================================
# 关键词提取的正则模式
# ============================================================

# 停用词（规则模式 tag 提取时跳过）
_STOP_WORDS: frozenset[str] = frozenset({
    # 中文停用词
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "它", "他", "她", "们", "为", "与", "或",
    "及", "以", "但", "而", "从", "对", "等", "被", "把", "向", "可以", "这是",
    # 英文停用词
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "shall", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "and", "or", "not",
    "but", "if", "then", "else", "when", "where", "why", "how", "all",
    "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "only", "own", "same", "so", "than", "too", "very",
    "this", "that", "these", "those", "it", "its", "i", "you", "he",
    "she", "we", "they", "what", "which", "who", "whom",
})

# Markdown 标题行：# 标题
_MARKDOWN_HEADING = re.compile(r'^#+\s+(.+?)\s*$', re.MULTILINE)

# 中英文词提取（2-6 字的中文词组 或 3+ 字母英文词）
_CJK_WORD = re.compile(r'[\u4e00-\u9fff]{2,6}')
_EN_WORD = re.compile(r'[a-zA-Z]{3,}')

# 句子提取（以。！？.!? 结尾的句子）
_SENTENCE_END = re.compile(r'[。！？.!?]')


# ============================================================
# MetadataEnricher — 规则增强 + 可选 LLM 增强
# ============================================================

class MetadataEnricher(BaseTransform):
    """Chunk 元数据增强器 — 生成 title/summary/tags

    知识点：规则模式与 LLM 模式的对比
      - 规则模式：基于文本统计（首行/词频/前N字），零成本、确定性、语义弱
      - LLM 模式：基于语义理解，成本高、非确定性、语义强
      - 降级策略：LLM 失败 → 使用规则结果，metadata 标记 enriched_by="rule"

    接口签名：
      MetadataEnricher(settings, llm=None, prompt_path=None)
    """

    # 内置 fallback prompt（prompt 文件读取失败时使用）
    _DEFAULT_PROMPT = (
        "请分析以下文本，提取三个字段：\n"
        "1. title: 简洁概括片段主题（不超过20字）\n"
        "2. summary: 内容摘要（50-100字）\n"
        "3. tags: 3-5个关键词标签\n\n"
        "输出 JSON 格式：\n"
        '{"title": "...", "summary": "...", "tags": ["...", "..."]}\n\n'
        "文本片段：\n{text}\n"
    )

    # 规则模式 summary 最大长度
    _RULE_SUMMARY_MAX = 100

    def __init__(
        self,
        settings: Settings,
        llm: BaseLLM | None = None,
        prompt_path: str | None = None,
    ) -> None:
        """初始化 MetadataEnricher"""
        self._settings = settings

        enricher_cfg = settings.ingestion.metadata_enricher
        self._use_llm: bool = enricher_cfg.use_llm
        self._max_tags: int = enricher_cfg.max_tags if enricher_cfg.max_tags > 0 else 5

        # prompt 路径优先级：构造参数 > 配置文件
        self._prompt_path: str = prompt_path or enricher_cfg.prompt_path
        self._prompt_template: str = self._load_prompt(self._prompt_path)

        # LLM 实例：注入优先；未注入且 use_llm=True 时从工厂创建
        self._llm: BaseLLM | None = llm
        if self._use_llm and self._llm is None:
            try:
                self._llm = LLMFactory.create(settings.llm)
            except LLMError as e:
                logger.warning("MetadataEnricher: LLM 创建失败，降级为纯规则模式: %s", e)
                self._use_llm = False
                self._llm = None

    # --------------------------------------------------------
    # 主入口：transform
    # --------------------------------------------------------

    def transform(
        self,
        chunks: list[Chunk],
        trace: TraceContext | None = None,
    ) -> list[Chunk]:
        """对 chunk 列表执行元数据增强

        接口签名：transform(chunks, trace=None) -> list[Chunk]
        出参：增强后的 Chunk 列表（新对象，输入不可变）

        异常隔离：单个 chunk 处理异常 → 保留原文 + metadata 标记，不影响其他 chunk
        """
        if not isinstance(chunks, list):
            raise TransformError(f"chunks 必须是 list，得到 {type(chunks).__name__}")

        enriched: list[Chunk] = []
        for chunk in chunks:
            try:
                enriched.append(self._enrich_single(chunk, trace))
            except Exception as e:  # noqa: BLE001
                logger.warning("MetadataEnricher: chunk %s 处理异常，保留原文: %s", chunk.chunk_id, e)
                fallback_meta = dict(chunk.metadata)
                fallback_meta["enriched_by"] = "error"
                fallback_meta["enrichment_fallback"] = f"exception: {e}"
                enriched.append(replace(chunk, metadata=fallback_meta))

        if trace is not None:
            trace.record_stage(
                "metadata_enricher",
                {
                    "total": len(enriched),
                    "enriched_by_llm": sum(
                        1 for c in enriched if c.metadata.get("enriched_by") == "llm"
                    ),
                    "enriched_by_rule": sum(
                        1 for c in enriched if c.metadata.get("enriched_by") == "rule"
                    ),
                    "use_llm": self._use_llm,
                },
            )

        return enriched

    # --------------------------------------------------------
    # 单 chunk 处理
    # --------------------------------------------------------

    def _enrich_single(self, chunk: Chunk, trace: TraceContext | None) -> Chunk:
        """处理单个 chunk：规则增强 → 可选 LLM 增强 → 降级"""
        # 第一步：规则增强（始终执行）
        rule_meta = self._rule_based_enrich(chunk.text)

        new_metadata = dict(chunk.metadata)

        if not self._use_llm or self._llm is None:
            # 纯规则模式
            new_metadata["title"] = rule_meta["title"]
            new_metadata["summary"] = rule_meta["summary"]
            new_metadata["tags"] = rule_meta["tags"]
            new_metadata["enriched_by"] = "rule"
            return replace(chunk, metadata=new_metadata)

        # 第二步：LLM 增强
        llm_meta, fallback_reason = self._llm_enrich(chunk.text, trace)

        if llm_meta is not None:
            new_metadata["title"] = llm_meta.get("title", rule_meta["title"])
            new_metadata["summary"] = llm_meta.get("summary", rule_meta["summary"])
            tags = llm_meta.get("tags", rule_meta["tags"])
            if isinstance(tags, list):
                tags = [str(t) for t in tags[:self._max_tags]]
            else:
                tags = rule_meta["tags"]
            new_metadata["tags"] = tags
            new_metadata["enriched_by"] = "llm"
            return replace(chunk, metadata=new_metadata)

        # 降级：LLM 失败 → 使用规则结果
        new_metadata["title"] = rule_meta["title"]
        new_metadata["summary"] = rule_meta["summary"]
        new_metadata["tags"] = rule_meta["tags"]
        new_metadata["enriched_by"] = "rule"
        new_metadata["enrichment_fallback"] = fallback_reason or "llm_unavailable"
        return replace(chunk, metadata=new_metadata)

    # --------------------------------------------------------
    # 规则增强
    # --------------------------------------------------------

    def _rule_based_enrich(self, text: str) -> dict[str, Any]:
        """规则增强 — 基于文本统计提取 title/summary/tags

        接口签名：_rule_based_enrich(text: str) -> dict
        出参：{"title": str, "summary": str, "tags": list[str]}

        规则：
          - title: 首个 Markdown 标题 / 首行（截断20字）
          - summary: 前 N 字（截断到句子边界，最多100字）
          - tags: 词频最高的 3-5 个关键词（去停用词）
        """
        if not text:
            return {"title": "(空)", "summary": "", "tags": []}

        # title: 首个 Markdown 标题，否则首行非空内容
        title = self._extract_title(text)

        # summary: 前 N 字截断到句子边界
        summary = self._extract_summary(text, self._RULE_SUMMARY_MAX)

        # tags: 词频提取
        tags = self._extract_tags(text, self._max_tags)

        return {"title": title, "summary": summary, "tags": tags}

    def _extract_title(self, text: str) -> str:
        """提取 title：首个 Markdown 标题，否则首行"""
        match = _MARKDOWN_HEADING.search(text)
        if match:
            return match.group(1)[:20]

        # 首行非空内容
        for line in text.strip().split("\n"):
            line = line.strip()
            if line:
                # 去除 Markdown 前缀符号
                clean = re.sub(r'^[-*#>\d.]+\s*', '', line)
                if clean:
                    return clean[:20]
        return text[:20].strip()

    def _extract_summary(self, text: str, max_len: int) -> str:
        """提取 summary：前 N 字截断到句子边界"""
        clean = text.strip()
        if len(clean) <= max_len:
            return clean

        # 在 max_len 范围内找最后一个句子结束符
        segment = clean[:max_len]
        last_sentence_end = -1
        for m in _SENTENCE_END.finditer(segment):
            last_sentence_end = m.end()

        if last_sentence_end > 0:
            return clean[:last_sentence_end]
        # 没找到句子边界 → 直接截断
        return segment

    def _extract_tags(self, text: str, max_tags: int) -> list[str]:
        """提取 tags：词频最高的关键词（去停用词）"""
        # 提取中文词 + 英文词
        cjk_words = _CJK_WORD.findall(text)
        en_words = _EN_WORD.findall(text)
        all_words = cjk_words + [w.lower() for w in en_words]

        # 词频统计（去停用词 + 去单字符）
        word_freq: dict[str, int] = {}
        for word in all_words:
            word_lower = word.lower()
            if word_lower in _STOP_WORDS or len(word_lower) < 2:
                continue
            word_freq[word_lower] = word_freq.get(word_lower, 0) + 1

        # 按频率排序取前 N
        sorted_words = sorted(word_freq.items(), key=lambda x: (-x[1], x[0]))
        tags = [word for word, _ in sorted_words[:max_tags]]

        # 兜底：如果没有提取到 tags，用前几个词
        if not tags and all_words:
            tags = [w for w in all_words[:max_tags] if len(w) >= 2]

        return tags

    # --------------------------------------------------------
    # LLM 增强
    # --------------------------------------------------------

    def _llm_enrich(
        self, text: str, trace: TraceContext | None = None
    ) -> tuple[dict[str, Any] | None, str | None]:
        """LLM 语义增强 — 生成 title/summary/tags

        接口签名：_llm_enrich(text, trace) -> (metadata | None, fallback_reason | None)
        出参：
          - metadata: {"title": str, "summary": str, "tags": list[str]} 或 None
          - fallback_reason: 失败原因（成功时为 None）

        失败场景：
          1. LLMError — 网络/认证/限流
          2. 空响应 — LLM 返回空
          3. JSON 解析失败 — LLM 返回非 JSON
          4. 意外异常 — 兜底捕获
        """
        if not text:
            return None, "empty_input"

        prompt = self._prompt_template.replace("{text}", text)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "你是元数据提取专家，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self._llm.chat(messages)  # type: ignore[union-attr]
        except LLMError as e:
            reason = f"llm_error: {e}"
            logger.warning("MetadataEnricher: LLM 调用失败，降级: %s", e)
            if trace is not None:
                trace.record_stage("metadata_enricher.llm_error", {"reason": reason})
            return None, reason
        except Exception as e:  # noqa: BLE001
            reason = f"llm_unexpected_error: {e}"
            if trace is not None:
                trace.record_stage("metadata_enricher.llm_error", {"reason": reason})
            return None, reason

        # 空响应
        if not response or not response.strip():
            reason = "llm_empty_response"
            if trace is not None:
                trace.record_stage("metadata_enricher.llm_error", {"reason": reason})
            return None, reason

        # JSON 解析
        metadata = self._parse_llm_response(response)
        if metadata is None:
            reason = "llm_json_parse_error"
            if trace is not None:
                trace.record_stage("metadata_enricher.llm_error", {"reason": reason})
            return None, reason

        return metadata, None

    def _parse_llm_response(self, response: str) -> dict[str, Any] | None:
        """解析 LLM 返回的 JSON 响应

        知识点：LLM 输出不可靠，需要容错解析
          - 尝试直接 json.loads
          - 失败则尝试提取 { ... } 部分
          - 再失败则返回 None
        """
        text = response.strip()

        # 尝试直接解析
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

        # 尝试提取 JSON 块（LLM 可能在 JSON 前后加了文字）
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        # 尝试提取 ```json ... ``` 块
        code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if code_match:
            try:
                data = json.loads(code_match.group(1))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    # --------------------------------------------------------
    # Prompt 加载
    # --------------------------------------------------------

    def _load_prompt(self, prompt_path: str | None = None) -> str:
        """从文件加载 prompt 模板（支持默认 fallback）"""
        if prompt_path:
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    return content
                logger.warning("MetadataEnricher: prompt 文件为空: %s，使用内置默认", prompt_path)
            except OSError as e:
                logger.warning(
                    "MetadataEnricher: prompt 文件读取失败: %s (%s)，使用内置默认",
                    prompt_path, e,
                )
        return self._DEFAULT_PROMPT

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def use_llm(self) -> bool:
        """是否启用 LLM 增强"""
        return self._use_llm

    @property
    def prompt_template(self) -> str:
        """当前使用的 prompt 模板"""
        return self._prompt_template

