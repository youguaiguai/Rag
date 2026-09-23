"""
BM25Indexer — 倒排索引构建与持久化

知识点：BM25Indexer 在 RAG Pipeline 中的位置
  - 摄取链路：... → SparseEncoder → **BM25Indexer** → data/db/bm25/
  - 检索链路：query → tokenizer → **BM25Indexer.search()** → top_k chunk_ids
  - 职责：接收 SparseVector 列表，计算 IDF，构建倒排索引，持久化到文件系统

倒排索引结构（面试考点）：
  {
    "N": 文档总数,
    "avgdl": 平均文档长度,
    "k1": 1.2,
    "b": 0.75,
    "index": {
      "term1": {
        "idf": 1.23,
        "postings": [
          {"chunk_id": "c_0001", "tf": 3, "doc_length": 10},
          {"chunk_id": "c_0003", "tf": 1, "doc_length": 8},
        ]
      },
      "term2": { ... }
    }
  }

接口签名：
  BM25Indexer(persist_path: str = "data/db/bm25", k1: float = 1.2, b: float = 0.75)
  build(vectors: list[SparseVector]) -> None
  load() -> None
  search(query_terms: dict[str, float], top_k: int = 10) -> list[tuple[str, float]]
  rebuild(vectors: list[SparseVector]) -> None  # 重建（先清空再 build）
  upsert(vectors: list[SparseVector]) -> None   # 增量更新
"""

from __future__ import annotations

import json
import logging
import math
from ingestion.embedding.sparse_encoder import SparseVector
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.trace.trace_context import TraceContext

logger = logging.getLogger(__name__)


# ============================================================
# 倒排索引数据结构
# ============================================================

# 单个 posting 条目：{chunk_id, tf, doc_length}
Posting = dict[str, Any]

# 倒排索引项：{idf, postings}
IndexEntry = dict[str, Any]

# 完整索引：{N, avgdl, k1, b, index: {term: IndexEntry}}
IndexData = dict[str, Any]


# ============================================================
# BM25Indexer — 倒排索引构建与持久化
# ============================================================

class BM25Indexer:
    """BM25 倒排索引构建器 — 接收 SparseVector，构建索引，持久化

    知识点：倒排索引 vs 正排索引
      - 正排索引：chunk_id → terms（"这个 chunk 有哪些词"）
      - 倒排索引：term → postings（"这个词在哪些 chunk 中出现"）
      - 检索用倒排索引：query 的 term → 直接查到包含该 term 的文档
      - 面试考点："为什么叫倒排？" → 反转了映射方向（term→doc 而非 doc→term）

    接口签名：
      BM25Indexer(persist_path, k1, b)
      build(vectors) → 构建索引
      load() → 从文件加载
      search(query_terms, top_k) → 查询返回 [(chunk_id, score), ...]
      rebuild(vectors) → 清空重建
      upsert(vectors) → 增量更新
    """

    # 索引文件名
    INDEX_FILENAME = "bm25_index.json"

    def __init__(
        self,
        persist_path: str = "data/db/bm25",
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        """初始化 BM25Indexer

        接口签名：BM25Indexer(persist_path="data/db/bm25", k1=1.2, b=0.75)
        入参：
          - persist_path: 索引持久化目录
          - k1: BM25 词频饱和参数（默认 1.2）
          - b: BM25 长度归一化参数（默认 0.75）
        """
        self._persist_dir = Path(persist_path)
        self._index_path = self._persist_dir / self.INDEX_FILENAME
        self._k1 = k1
        self._b = b

        # 内存中的索引数据
        self._index: IndexData = {
            "N": 0,
            "avgdl": 0.0,
            "k1": k1,
            "b": b,
            "index": {},  # term → {idf, postings: [...]}
        }

        # chunk_id → doc_length 的映射（用于增量更新时查找旧文档长度）
        self._doc_lengths: dict[str, int] = {}

    # --------------------------------------------------------
    # 构建索引
    # --------------------------------------------------------

    def build(
        self,
        vectors: list[SparseVector],
        trace: TraceContext | None = None,
    ) -> None:
        """从 SparseVector 列表构建完整倒排索引

        接口签名：build(vectors: list[SparseVector], trace=None) -> None
        入参：
          - vectors: SparseEncoder 输出的稀疏向量列表
          - trace: 可选追踪上下文

        处理流程：
          1. 计算语料库统计（N、avgdl、DF）
          2. 计算 IDF
          3. 构建倒排索引（term → postings）
          4. 持久化到文件

        知识点：build 是全量构建，不保留旧索引
          - 首次索引构建用 build
          - 后续增量更新用 upsert
          - 面试考点："build 和 upsert 的区别？" → build 清空重建，upsert 增量
        """
        # 清空旧索引
        self._index = {
            "N": 0,
            "avgdl": 0.0,
            "k1": self._k1,
            "b": self._b,
            "index": {},
        }
        self._doc_lengths = {}

        if not vectors:
            self._save()
            if trace is not None:
                trace.record_stage("bm25_indexer", {
                    "operation": "build",
                    "N": 0,
                    "terms": 0,
                })
            return

        # 构建正排索引（chunk_id → terms）用于后续 upsert
        for vec in vectors:
            self._doc_lengths[vec.chunk_id] = vec.doc_len

        # 计算语料库统计
        N = len(vectors)
        total_len = sum(v.doc_len for v in vectors)
        avgdl = total_len / N

        # DF 统计
        df: dict[str, int] = {}
        for vec in vectors:
            for term in vec.terms:
                df[term] = df.get(term, 0) + 1

        # IDF 预计算
        idf_map: dict[str, float] = {}
        for term, n in df.items():
            idf_map[term] = self._compute_idf(n, N)

        # 构建倒排索引
        inverted: dict[str, IndexEntry] = {}
        for term, idf in idf_map.items():
            inverted[term] = {"idf": idf, "postings": []}

        for vec in vectors:
            for term, tf in vec.terms.items():
                if term in inverted:
                    inverted[term]["postings"].append({
                        "chunk_id": vec.chunk_id,
                        "tf": float(tf),
                        "doc_length": vec.doc_len,
                    })

        self._index = {
            "N": N,
            "avgdl": avgdl,
            "k1": self._k1,
            "b": self._b,
            "index": inverted,
        }

        # 持久化
        self._save()

        if trace is not None:
            trace.record_stage("bm25_indexer", {
                "operation": "build",
                "N": N,
                "avgdl": round(avgdl, 2),
                "terms": len(inverted),
            })

        logger.info(
            "BM25Indexer: build 完成，N=%d, avgdl=%.1f, %d 个 term",
            N, avgdl, len(inverted),
        )

    # --------------------------------------------------------
    # 增量更新
    # --------------------------------------------------------

    def upsert(
        self,
        vectors: list[SparseVector],
        trace: TraceContext | None = None,
    ) -> None:
        """增量更新索引（新增/更新文档）

        接口签名：upsert(vectors: list[SparseVector], trace=None) -> None

        知识点：增量更新策略
          1. 如果 chunk_id 已存在 → 先删除旧文档的 postings，再插入新的
          2. 如果 chunk_id 不存在 → 直接插入
          3. 更新后重新计算 N、avgdl、DF、IDF
          4. 面试考点："增量更新为什么要重算 IDF？" → 新文档改变了 N 和 DF，IDF 依赖它们

        简化实现：收集所有已有 + 新增的 SparseVector，重新 build
        （生产环境可优化为增量计算，但正确性不变）
        """
        if not vectors:
            return

        # 收集需要重建的所有文档
        # 从现有索引中提取已有文档的 SparseVector
        existing_vectors = self._extract_vectors_from_index()

        # 更新/新增
        new_chunk_ids = {v.chunk_id for v in vectors}
        merged = [v for v in existing_vectors if v.chunk_id not in new_chunk_ids]
        merged.extend(vectors)

        # 重新构建
        self.build(merged, trace=trace)

        logger.info(
            "BM25Indexer: upsert %d 文档（合并后 %d 文档）",
            len(vectors), len(merged),
        )

    # --------------------------------------------------------
    # 重建
    # --------------------------------------------------------

    def rebuild(
        self,
        vectors: list[SparseVector],
        trace: TraceContext | None = None,
    ) -> None:
        """重建索引（清空旧索引后全量构建）

        接口签名：rebuild(vectors, trace=None) -> None
        等同于 build()，语义更清晰（用于手动重建场景）
        """
        self.build(vectors, trace=trace)

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------

    def search(
        self,
        query_terms: dict[str, float],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """BM25 查询 — 返回 top_k 文档

        接口签名：search(query_terms: dict[str, float], top_k=10) -> list[tuple[str, float]]
        入参：
          - query_terms: 查询词频 {term: tf}
          - top_k: 返回前 K 个结果
        出参：[(chunk_id, score), ...] 按分数降序排列

        处理流程：
          1. 对每个 query term 查倒排索引
          2. 累加每个文档的 BM25 分数
          3. 按分数排序取 top_k

        知识点：倒排索引查询效率
          - 只遍历包含 query term 的文档（非全量扫描）
          - 复杂度 O(Σ |postings(term)|) 而非 O(N)
          - 面试考点："为什么倒排索引快？" → 只扫描相关文档
        """
        if not query_terms or self._index["N"] == 0:
            return []

        avgdl = self._index["avgdl"]
        k1 = self._index["k1"]
        b = self._index["b"]
        inverted = self._index["index"]

        # 累加分数
        scores: dict[str, float] = {}

        for term, q_tf in query_terms.items():
            if term not in inverted:
                continue

            entry = inverted[term]
            idf = entry["idf"]

            for posting in entry["postings"]:
                chunk_id = posting["chunk_id"]
                tf = posting["tf"]
                doc_len = posting["doc_length"]

                # BM25 TF 组件
                if avgdl > 0:
                    tf_component = (tf * (k1 + 1)) / (
                        tf + k1 * (1 - b + b * doc_len / avgdl)
                    )
                else:
                    tf_component = (tf * (k1 + 1)) / (tf + k1)

                score = idf * tf_component
                scores[chunk_id] = scores.get(chunk_id, 0) + score

        # 排序取 top_k
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        return ranked[:top_k]

    def query(
        self,
        keywords: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """BM25 关键词查询 — 接受关键词列表，返回结构化结果

        接口签名：query(keywords: list[str], top_k=10) -> list[dict]
        入参：
          - keywords: 关键词列表（如 QueryProcessor 提取的 keywords）
          - top_k: 返回前 K 个结果
        入参：
          - keywords: 关键词列表（如 QueryProcessor 提取的 keywords）
          - top_k: 返回前 K 个结果
        出参：[{"chunk_id": str, "score": float}, ...] 按分数降序

        知识点：query() vs search()
          - search()：底层接口，接受 query_terms: dict[str, float]（TF 加权）
          - query()：便捷接口，接受 keywords: list[str]（简单计数 TF）
          - query() 内部调用 search()，自动统计词频

        处理流程：
          1. 将 keywords 统计词频 → query_terms: dict[str, float]
          2. 调用 self.search(query_terms, top_k)
          3. 转换 list[tuple] → list[dict]（结构化输出）
        """
        if not keywords:
            return []

        # 统计词频
        query_terms: dict[str, float] = {}
        for kw in keywords:
            query_terms[kw] = query_terms.get(kw, 0) + 1.0

        # 调用底层 search
        results = self.search(query_terms, top_k)

        # 转换为结构化输出
        return [
            {"chunk_id": chunk_id, "score": score}
            for chunk_id, score in results
        ]

    # --------------------------------------------------------
    # 持久化：save / load
    # --------------------------------------------------------

    def _save(self) -> None:
        """将索引序列化到文件"""
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False)
        logger.debug("BM25Indexer: 索引已保存到 %s", self._index_path)

    def load(self) -> None:
        """从文件加载索引

        接口签名：load() -> None
        异常：FileNotFoundError — 索引文件不存在

        知识点：序列化格式选择
          - JSON：可读性好、调试方便、跨语言兼容
          - 生产环境可用 pickle/binary 提升性能
          - 面试考点："为什么用 JSON 而非 pickle？" → 可读性 + 安全性
        """
        if not self._index_path.exists():
            raise FileNotFoundError(f"BM25 索引文件不存在: {self._index_path}")

        with open(self._index_path, "r", encoding="utf-8") as f:
            self._index = json.load(f)

        # 重建 doc_lengths 映射
        self._doc_lengths = {}
        for term_entry in self._index["index"].values():
            for posting in term_entry["postings"]:
                self._doc_lengths[posting["chunk_id"]] = posting["doc_length"]

        logger.info(
            "BM25Indexer: 索引已加载，N=%d, %d 个 term",
            self._index["N"], len(self._index["index"]),
        )

    # --------------------------------------------------------
    # 辅助方法
    # --------------------------------------------------------

    def _compute_idf(self, df: int, N: int) -> float:
        """计算 IDF

        接口签名：_compute_idf(df: int, N: int) -> float
        公式：IDF = log((N - df + 0.5) / (df + 0.5) + 1)

        知识点：IDF 的变体
          - 标准 BM25 IDF: ln((N - df + 0.5) / (df + 0.5) + 1)
          - 经典 IDF: log(N / df)
          - 本项目用 BM25 变体（+1 防止负值）
          - 面试考点："+1 的作用？" → 防止 IDF 为负（当 df > N/2 时经典 IDF 会负）
        """
        if N == 0 or df == 0:
            return 0.0
        val = (N - df + 0.5) / (df + 0.5) + 1
        return math.log(val) if val > 0 else 0.0

    def _extract_vectors_from_index(self) -> list[SparseVector]:
        """从现有索引中提取 SparseVector 列表（用于增量更新重建）"""
        if self._index["N"] == 0:
            return []

        # chunk_id → (terms, doc_len)
        doc_terms: dict[str, dict[str, float]] = {}
        doc_lens: dict[str, int] = {}
        doc_ids: dict[str, str] = {}  # chunk_id → doc_id

        for term, entry in self._index["index"].items():
            for posting in entry["postings"]:
                cid = posting["chunk_id"]
                if cid not in doc_terms:
                    doc_terms[cid] = {}
                    doc_lens[cid] = posting["doc_length"]
                    doc_ids[cid] = cid  # doc_id 简化为 chunk_id
                doc_terms[cid][term] = posting["tf"]

        return [
            SparseVector(
                chunk_id=cid,
                doc_id=doc_ids.get(cid, cid),
                terms=terms,
                doc_len=doc_lens.get(cid, 0),
            )
            for cid, terms in doc_terms.items()
        ]

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def num_docs(self) -> int:
        """索引中的文档总数"""
        return self._index["N"]

    @property
    def num_terms(self) -> int:
        """索引中的 term 总数"""
        return len(self._index["index"])

    @property
    def avgdl(self) -> float:
        """平均文档长度"""
        return self._index["avgdl"]

    @property
    def index_path(self) -> Path:
        """索引文件路径"""
        return self._index_path

    @property
    def is_built(self) -> bool:
        """索引是否已构建（N > 0）"""
        return self._index["N"] > 0

    def remove_document(self, source_path: str) -> int:
        """按 source_path 删除文档对应的所有 chunk 向量

        接口签名：remove_document(source_path: str) -> int
        入参：source_path — 文档源路径
        出参：删除的向量数
        """
        if not self.is_built:
            return 0

        # 找到属于该文档的 chunk_id 列表
        doc_prefix = f"# chunk="
        ids_to_remove = [
            chunk_id for chunk_id in self._index["index"].get("doc_ids", {})
            if source_path in chunk_id
        ]

        # 更精确：遍历所有 term 的倒排列表，收集属于该文档的 id
        removed_count = 0
        all_chunk_ids = set()
        for term, posting in self._index.get("index", {}).items():
            if isinstance(posting, dict):
                for chunk_id in posting:
                    if chunk_id.startswith(source_path):
                        all_chunk_ids.add(chunk_id)

        # 倒序遍历 term 索引清除
        for chunk_id in all_chunk_ids:
            for term in list(self._index.get("index", {}).keys()):
                posting = self._index["index"].get(term, {})
                if isinstance(posting, dict) and chunk_id in posting:
                    del posting[chunk_id]
                    removed_count += 1

        if all_chunk_ids:
            self._save()

        return len(all_chunk_ids)

    def list_all_chunk_ids(self) -> list[str]:
        """列出所有 chunk ID（用于文档列表展示）"""
        if not self.is_built:
            return []

        all_ids = set()
        for term, posting in self._index.get("index", {}).items():
            if isinstance(posting, dict):
                all_ids.update(posting.keys())

        return sorted(all_ids)

