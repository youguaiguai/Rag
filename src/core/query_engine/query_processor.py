"""
QueryProcessor — 查询预处理（关键词提取 + filters 解析）

知识点：QueryProcessor 在 RAG 检索链路中的位置
  - 检索链路：Query → QueryProcessor → DenseRetriever + SparseRetriever → Fusion → Reranker
  - 职责：将用户原始查询字符串转化为结构化 ProcessedQuery
    1. 关键词提取 → 供 SparseRetriever（BM25）使用
    2. 原始查询保留 → 供 DenseRetriever（语义向量检索）使用
    3. filters 解析 → 供 HybridSearch（metadata 过滤）使用

关键词提取策略（与 SparseEncoder 分词策略对齐）：
  - 英文：正则提取 3+ 字母词，小写化，去停用词
  - 中文：Bigram（2-gram）策略，无需 jieba 外部依赖
  - 混合文本：英文词 + 中文 bigram 合并
  - 面试考点："为什么不用 jieba？" → 减少外部依赖 + bigram 足够用于 BM25 关键词检索

filters 解析策略（当前阶段最小实现）：
  - 接受 dict | None，统一输出 dict
  - None → {}（空 dict，不过滤）
  - dict → 原样透传（后续 HybridSearch 负责应用）
  - 面试考点："filters 是什么？" → metadata 过滤条件，如 {"doc_type": "pdf"}

降级策略：
  - QueryProcessor 是检索链路入口，Fail-Fast：空查询直接抛 ValueError
  - 关键词提取本身不会失败（纯本地计算，无外部 API）

接口签名：
  QueryProcessor(settings: Settings)
  process(query: str, filters: dict | None = None, trace: TraceContext | None = None) -> ProcessedQuery
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext

logger = logging.getLogger(__name__)


# ============================================================
# 停用词表（与 SparseEncoder 对齐）
# ============================================================

_EN_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "shall", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "and", "or", "not",
    "but", "if", "then", "else", "when", "where", "why", "how", "all",
    "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "only", "own", "same", "so", "than", "too", "very",
    "this", "that", "these", "those", "it", "its", "i", "you", "he",
    "she", "we", "they", "what", "which", "who", "whom", "in", "into",
})

# 英文词提取（3+ 字母，与 SparseEncoder 一致）
_EN_WORD_RE = re.compile(r"[a-zA-Z]{3,}")

# 中文 bigram 提取（连续中文字符 2-gram，与 SparseEncoder 一致）
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


# ============================================================
# QueryProcessor — 查询预处理器
# ============================================================

class QueryProcessor:
    """查询预处理器 — 关键词提取 + filters 解析

    知识点：QueryProcessor 的设计原则
      - 单一职责：只做查询预处理，不做检索（检索由 Dense/Sparse Retriever 负责）
      - 纯本地计算：关键词提取无需外部 API，不会失败
      - 与 SparseEncoder 分词策略对齐：保证查询和文档使用相同的分词方式
        → 面试考点："为什么查询和文档分词策略必须一致？" → BM25 匹配依赖词项对齐

    接口签名：
      QueryProcessor(settings: Settings)
      process(query, filters=None, trace=None) -> ProcessedQuery
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 QueryProcessor

        接口签名：QueryProcessor(settings: Settings)
        入参：
          - settings: 全局配置（QueryProcessor 当前不需要额外配置，纯本地计算）
        """
        self._settings = settings

    # --------------------------------------------------------
    # 主入口：process
    # --------------------------------------------------------

    def process(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        trace: TraceContext | None = None,
    ) -> Any:
        """处理用户查询，返回 ProcessedQuery

        接口签名：process(query, filters=None, trace=None) -> ProcessedQuery
        入参：
          - query: 用户查询字符串（非空）
          - filters: 可选的 metadata 过滤条件（如 {"doc_type": "pdf"}）
          - trace: 可选的追踪上下文
        出参：ProcessedQuery（包含 raw_query, keywords, filters）
        异常：ValueError — 查询为空或非字符串

        处理流程：
          1. 校验 query 非空
          2. 提取关键词（英文 3+ 字母词 + 中文 bigram，去停用词）
          3. 解析 filters（None → {}，dict → 原样透传）
          4. 记录 trace
          5. 返回 ProcessedQuery

        面试考点：
          "QueryProcessor 输出了什么？" → ProcessedQuery（raw_query + keywords + filters）
          "keywords 给谁用？" → SparseRetriever（BM25 检索）
          "raw_query 给谁用？" → DenseRetriever（语义向量检索）
        """
        import time

        from core.types import ProcessedQuery

        start = time.perf_counter()

        # 1. 校验查询
        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "查询不能为空，必须是非空字符串"
                f"（收到 type={type(query).__name__}, len={len(query) if isinstance(query, str) else 'N/A'}）"
            )

        # 去除首尾空白
        raw_query = query.strip()

        # 2. 提取关键词
        keywords = self._extract_keywords(raw_query)

        # 3. 解析 filters
        parsed_filters = self._parse_filters(filters)

        # 4. 记录 trace
        if trace is not None:
            duration_ms = (time.perf_counter() - start) * 1000
            trace.record_stage(
                "query_processor",
                {
                    "raw_query": raw_query,
                    "keywords_count": len(keywords),
                    "keywords": keywords[:20],  # 截断防止过长
                    "filters": list(parsed_filters.keys()),
                },
                duration_ms=round(duration_ms, 2),
            )

        logger.debug(
            "QueryProcessor: query=%r → keywords=%d, filters=%d",
            raw_query[:100],
            len(keywords),
            len(parsed_filters),
        )

        return ProcessedQuery(
            raw_query=raw_query,
            keywords=keywords,
            filters=parsed_filters,
        )

    # --------------------------------------------------------
    # 关键词提取（规则/分词）
    # --------------------------------------------------------

    def _extract_keywords(self, query: str) -> list[str]:
        """从查询字符串中提取关键词

        接口签名：_extract_keywords(query: str) -> list[str]
        入参：查询字符串（已 strip）
        出参：关键词列表（去停用词，保留顺序，去重）

        知识点：分词策略（与 SparseEncoder._tokenize 对齐）
          - 英文：正则 [a-zA-Z]{3,} 提取 3+ 字母词，小写化，去停用词
          - 中文：Bigram（2-gram）策略，连续中文字符两两组合
          - 去重：同一关键词只保留首次出现（保持顺序）
          - 面试考点："为什么英文要 3+ 字母？" → 过滤无意义的短词（如 "to", "is"）

        注意：与 SparseEncoder._tokenize 的差异
          - SparseEncoder 输出 tokens（允许重复，用于词频统计）
          - QueryProcessor 输出 keywords（去重，用于 BM25 查询）
          → 面试考点："为什么查询端去重而文档端不去重？" → 查询端只检索，文档端需要词频
        """
        keywords: list[str] = []
        seen: set[str] = set()

        # 英文词提取
        for m in _EN_WORD_RE.finditer(query):
            word = m.group().lower()
            if word not in _EN_STOP_WORDS and word not in seen:
                seen.add(word)
                keywords.append(word)

        # 中文 bigram 提取
        for run_match in _CJK_RUN_RE.finditer(query):
            run = run_match.group()
            if len(run) < 2:
                continue
            for i in range(len(run) - 1):
                bigram = run[i:i + 2]
                if bigram not in seen:
                    seen.add(bigram)
                    keywords.append(bigram)

        return keywords

    # --------------------------------------------------------
    # filters 解析
    # --------------------------------------------------------

    def _parse_filters(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        """解析 filters 结构

        接口签名：_parse_filters(filters: dict | None) -> dict
        入参：filters（dict 或 None）
        出参：dict（None → 空字典，dict → 原样返回）

        知识点：filters 的设计
          - 当前阶段最小实现：None → {}，dict → 原样透传
          - 后续可扩展：支持字符串解析（如 "doc_type:pdf"）、嵌套条件等
          - filters 由 HybridSearch 应用到向量库的 metadata 过滤
          - 面试考点："filters 是什么？" → metadata 过滤条件，如 {"doc_type": "pdf"}

        校验逻辑：
          - None → 返回 {}
          - dict → 原样返回（浅拷贝避免外部修改）
          - 其他类型 → 记录警告，返回 {}（容错降级）
        """
        if filters is None:
            return {}

        if isinstance(filters, dict):
            return dict(filters)  # 浅拷贝，避免外部修改影响内部状态

        # 非 dict 类型，容错降级
        logger.warning(
            "filters 类型不是 dict（收到 %s），降级为空过滤条件",
            type(filters).__name__,
        )
        return {}

