"""
SparseEncoder — 稀疏向量编码（BM25 统计）

知识点：SparseEncoder 在 RAG Pipeline 中的位置
  - 摄取链路：Loader → Splitter → Transform 链 → DenseEncoder + **SparseEncoder** → Storage
  - 职责：对 chunks 进行分词，统计词频(TF)，输出 term weights 结构
  - 与 DenseEncoder 互补：Dense 捕获语义相似性，Sparse 捕获精确匹配

BM25 核心公式（面试考点）：
  Score(D, Q) = Σ IDF(qi) · (f(qi,D)·(k1+1)) / (f(qi,D)+k1·(1-b+b·|D|/avgdl))

  其中：
  - f(qi,D): 词 qi 在文档 D 中的频率（TF）
  - |D|: 文档 D 的长度（token 数）
  - avgdl: 语料库平均文档长度
  - IDF(qi) = ln((N - n(qi) + 0.5) / (n(qi) + 0.5) + 1)
  - k1=1.2, b=0.75（标准参数）

输出结构 SparseVector:
  - chunk_id: 对应的 chunk ID
  - terms: dict[str, float] — term → tf（词频，后续 bm25_indexer 计算 BM25 score）

分词策略（无外部分词器依赖）：
  - 英文：按空格/标点分词，小写化，去停用词
  - 中文：Bigram（2-gram）策略，无需 jieba 依赖
  - 混合文本：英文词 + 中文 bigram 合并

接口签名：
  SparseEncoder(settings: Settings)
  encode(chunks: list[Chunk], trace: TraceContext | None = None) -> list[SparseVector]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from core.types import Chunk

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构：SparseVector — BM25 统计输出
# ============================================================

@dataclass
class SparseVector:
    """稀疏向量 — BM25 统计结果（单个 chunk 的词频统计）

    知识点：SparseVector vs DenseVector
      - DenseVector: list[float]，维度固定（如 1536），每维都有值
      - SparseVector: dict[str, float]，只存储非零项，维度不固定
      - 面试考点："为什么叫稀疏？" → 大部分词不在单个文档中出现，非零项很少

    接口签名：SparseVector(chunk_id, doc_id, terms, doc_len)
    字段说明：
      - chunk_id: 对应的 chunk ID（与 ChunkRecord.chunk_id 一致）
      - doc_id: 所属文档 ID
      - terms: {term: tf} 词频映射（后续 bm25_indexer 用于计算 BM25 score）
      - doc_len: 文档长度（token 数，用于 BM25 长度归一化）

    与 BM25 的关系：
      - terms 提供词频 f(qi, D)
      - doc_len 提供文档长度 |D|
      - bm25_indexer 汇总所有 SparseVector 计算 DF、avgdl、IDF
    """
    chunk_id: str
    doc_id: str
    terms: dict[str, float] = field(default_factory=dict)
    doc_len: int = 0


# ============================================================
# 分词工具
# ============================================================

# 英文停用词（与 MetadataEnricher 中的停用词表对齐）
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

# 英文词提取（3+ 字母）
_EN_WORD_RE = re.compile(r'[a-zA-Z]{3,}')

# 中文字符范围
_CJK_RE = re.compile(r'[\u4e00-\u9fff]')

# 中文 bigram 提取（连续中文字符 2-gram）
_CJK_RUN_RE = re.compile(r'[\u4e00-\u9fff]+')


def _tokenize(text: str) -> list[str]:
    """分词：英文词 + 中文 bigram

    知识点：分词策略选择
      - 英文：空格/标点天然分词，取 3+ 字母词，去停用词
      - 中文：无分词器依赖，用 Bigram（2-gram）捕获部分语义
      - Bigram 局限：无语义分词能力（"向量数据库" → "向量", "量数", "数据", "据库"）
      - 面试考点："为什么不用 jieba？" → 减少外部依赖 + bigram 足够用于 BM25 统计

    接口签名：_tokenize(text: str) -> list[str]
    出参：token 列表（已去停用词）
    """
    tokens: list[str] = []

    # 英文词提取
    for m in _EN_WORD_RE.finditer(text):
        word = m.group().lower()
        if word not in _EN_STOP_WORDS:
            tokens.append(word)

    # 中文 bigram 提取
    for run_match in _CJK_RUN_RE.finditer(text):
        run = run_match.group()
        if len(run) < 2:
            continue
        for i in range(len(run) - 1):
            tokens.append(run[i:i + 2])

    return tokens


# ============================================================
# SparseEncoder — BM25 统计编码器
# ============================================================

class SparseEncoder:
    """稀疏向量编码器 — 对 chunks 进行分词和 BM25 统计

    知识点：SparseEncoder 与 DenseEncoder 的对比
      | 维度 | DenseEncoder | SparseEncoder |
      |------|-------------|--------------|
      | 输出 | list[float]（固定维度） | dict[str, float]（可变维度） |
      | 语义 | 语义相似性 | 精确匹配 |
      | 依赖 | Embedding API（外部） | 纯本地计算（无 API） |
      | 失败策略 | 抛异常（API 不可用） | 不会失败（本地计算） |
      | 用途 | 向量数据库 | BM25 倒排索引 |

    接口签名：
      SparseEncoder(settings: Settings)
      encode(chunks, trace=None) -> list[SparseVector]
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 SparseEncoder

        接口签名：SparseEncoder(settings: Settings)
        入参：
          - settings: 全局配置（SparseEncoder 不需要额外配置，纯本地计算）
        """
        self._settings = settings

    # --------------------------------------------------------
    # 主入口：encode
    # --------------------------------------------------------

    def encode(
        self,
        chunks: list[Chunk],
        trace: TraceContext | None = None,
    ) -> list[SparseVector]:
        """对 Chunk 列表执行分词和词频统计

        接口签名：encode(chunks: list[Chunk], trace=None) -> list[SparseVector]
        入参：
          - chunks: 待编码的 Chunk 列表
          - trace: 可选追踪上下文
        出参：SparseVector 列表（数量与输入一致）

        处理流程：
          1. 空列表 → 返回空列表
          2. 逐 chunk 分词 → 统计词频 → 构建 SparseVector
          3. trace 记录阶段数据（总 chunk 数、总 token 数、平均文档长度）

        空文本处理：
          - 空文本 → terms={}, doc_len=0（BM25 索引器可处理空文档）
          - 面试考点："空文本怎么处理？" → 输出空 terms，doc_len=0，不抛异常
        """
        # 1. 空输入
        if not chunks:
            if trace is not None:
                trace.record_stage("sparse_encoder", {"total": 0, "avg_doc_len": 0})
            return []

        # 2. 逐 chunk 编码
        vectors: list[SparseVector] = []
        total_tokens = 0

        for chunk in chunks:
            vec = self._encode_single(chunk)
            vectors.append(vec)
            total_tokens += vec.doc_len

        # 3. trace 记录
        avg_doc_len = total_tokens / len(vectors) if vectors else 0
        if trace is not None:
            trace.record_stage(
                "sparse_encoder",
                {
                    "total": len(vectors),
                    "total_tokens": total_tokens,
                    "avg_doc_len": round(avg_doc_len, 2),
                    "unique_terms": len(set(
                        term for vec in vectors for term in vec.terms
                    )),
                },
            )

        logger.info(
            "SparseEncoder: 编码完成，%d 个 chunk，平均文档长度 %.1f tokens",
            len(vectors),
            avg_doc_len,
        )

        return vectors

    # --------------------------------------------------------
    # 单 chunk 编码
    # --------------------------------------------------------

    def _encode_single(self, chunk: Chunk) -> SparseVector:
        """处理单个 chunk：分词 → 统计词频

        接口签名：_encode_single(chunk: Chunk) -> SparseVector
        出参：SparseVector（chunk_id, doc_id, terms, doc_len）
        """
        text = chunk.text

        # 空文本处理
        if not text or not text.strip():
            return SparseVector(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                terms={},
                doc_len=0,
            )

        # 分词
        tokens = _tokenize(text)

        # 词频统计
        terms: dict[str, float] = {}
        for token in tokens:
            terms[token] = terms.get(token, 0) + 1

        return SparseVector(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            terms=terms,
            doc_len=len(tokens),
        )

    # --------------------------------------------------------
    # 语料库统计（静态方法，供 bm25_indexer 调用）
    # --------------------------------------------------------

    @staticmethod
    def compute_corpus_stats(vectors: list[SparseVector]) -> dict[str, Any]:
        """计算语料库级统计（供 bm25_indexer 使用）

        接口签名：compute_corpus_stats(vectors) -> dict
        出参：
          {
            "N": 文档总数,
            "avgdl": 平均文档长度,
            "df": {term: 文档频率},  # 出现该 term 的文档数
            "idf": {term: IDF 值},   # 预计算的 IDF
          }

        知识点：BM25 的语料库统计
          - N: 文档总数（= len(vectors)）
          - avgdl: 平均文档长度（= Σ doc_len / N）
          - DF(term): 包含 term 的文档数
          - IDF(term) = ln((N - DF + 0.5) / (DF + 0.5) + 1)
          - 面试考点："IDF 为什么这样算？" → 词越稀有 IDF 越大，越重要
        """
        N = len(vectors)
        if N == 0:
            return {"N": 0, "avgdl": 0, "df": {}, "idf": {}}

        # 平均文档长度
        total_len = sum(v.doc_len for v in vectors)
        avgdl = total_len / N

        # 文档频率（DF）
        df: dict[str, int] = {}
        for vec in vectors:
            for term in vec.terms:
                df[term] = df.get(term, 0) + 1

        # IDF 预计算
        idf: dict[str, float] = {}
        for term, n in df.items():
            idf[term] = float(np_log((N - n + 0.5) / (n + 0.5) + 1))

        return {
            "N": N,
            "avgdl": avgdl,
            "df": df,
            "idf": idf,
        }

    @staticmethod
    def compute_bm25_score(
        query_terms: dict[str, float],
        doc_vector: SparseVector,
        corpus_stats: dict[str, Any],
        k1: float = 1.2,
        b: float = 0.75,
    ) -> float:
        """计算单个文档的 BM25 分数（供 sparse_retriever 使用）

        接口签名：compute_bm25_score(query_terms, doc_vector, corpus_stats, k1, b) -> float
        入参：
          - query_terms: 查询词频 {term: tf}
          - doc_vector: 文档的稀疏向量
          - corpus_stats: 语料库统计（compute_corpus_stats 输出）
          - k1: 词频饱和参数（默认 1.2）
          - b: 长度归一化参数（默认 0.75）
        出参：BM25 分数

        知识点：BM25 参数
          - k1 控制词频饱和：k1 越大，高频词增益越多（但趋于饱和）
          - b 控制长度归一化：b=1 完全归一化，b=0 不归一化
          - 面试考点："k1 和 b 的默认值？" → k1=1.2, b=0.75
        """
        idf_map = corpus_stats.get("idf", {})
        avgdl = corpus_stats.get("avgdl", 0)
        doc_len = doc_vector.doc_len

        score = 0.0
        for term, q_tf in query_terms.items():
            if term not in doc_vector.terms:
                continue
            if term not in idf_map:
                continue

            idf = idf_map[term]
            f = doc_vector.terms[term]

            # BM25 TF 组件
            if avgdl > 0:
                tf_component = (f * (k1 + 1)) / (
                    f + k1 * (1 - b + b * doc_len / avgdl)
                )
            else:
                tf_component = (f * (k1 + 1)) / (f + k1)

            score += idf * tf_component

        return score


# ============================================================
# 辅助：math.log 的安全封装（避免 import math 在类型检查中的问题）
# ============================================================

def np_log(x: float) -> float:
    """安全 log 计算（x <= 0 时返回 0）"""
    import math
    if x <= 0:
        return 0.0
    return math.log(x)

