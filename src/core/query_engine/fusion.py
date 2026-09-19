"""
结果融合 — RRF (Reciprocal Rank Fusion) 算法

知识点：RRF 的核心思想 — 不依赖分数的绝对值，只看排名
  - 公式：Score(d) = Σ 1/(k + rank_i(d))  （k 是平滑常数，通常 60）
  - 优势：Dense 和 Sparse 的分数量纲不同（余弦相似度 vs BM25 分数），
    直接加权融合不可行，RRF 通过排名归一化解决了这个问题
  - 面试考点："为什么用 RRF 而非加权求和？" → 不同检索引擎的分数不可比

RRF 算法详解（面试必须掌握）：
  输入：多路检索结果列表，如 [dense_results, sparse_results]
  每路结果已按自身分数降序排列（排名从 1 开始）

  对每个文档 d：
    rrf_score(d) = Σ_i 1/(k + rank_i(d))
    其中 k=60（平滑常数），rank_i(d) 是第 i 路中 d 的排名

  示例：
    dense:  [A(1), B(2), C(3)]   ← 排名 1, 2, 3
    sparse: [B(1), A(2), D(3)]   ← 排名 1, 2, 3

    A: 1/(60+1) + 1/(60+2) = 0.01639 + 0.01613 = 0.03252
    B: 1/(60+2) + 1/(60+1) = 0.01613 + 0.01639 = 0.03252  （同分！）
    C: 1/(60+3) + 0         = 0.01587
    D: 0         + 1/(60+3) = 0.01587

  最终排序：A ≈ B > C ≈ D

  面试考点："为什么 A 和 B 同分？" → 它们在两路中互换位置，贡献相同

k 参数选择：
  - k=60：标准值，Google 2022 年论文推荐
  - k 越小：对头部排名越敏感（第一名比第二名优势更大）
  - k 越大：排名贡献越平缓
  - 面试考点："k 参数的作用？" → 避免排名第一贡献过大

接口签名：
  Fusion(k: int = 60)
  fuse(lists: list[list[RetrievalResult]], top_k: int | None = None) -> list[RetrievalResult]
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Fusion:
    """结果融合器 — 使用 RRF 算法融合多路检索结果

    知识点：Fusion 在检索链路中的位置
      - 检索链路：QueryProcessor → DenseRetriever + SparseRetriever → **Fusion** → Reranker
      - 职责：将多路检索结果融合为统一的排序
      - 面试考点："Fusion 的作用？" → 多源结果融合，取长补短

    接口签名：
      Fusion(k: int = 60)
      fuse(lists: list[list[RetrievalResult]], top_k=None) -> list[RetrievalResult]
    """

    def __init__(self, k: int = 60) -> None:
        """初始化 Fusion

        接口签名：Fusion(k: int = 60)
        入参：
          - k: RRF 平滑常数（默认 60，Google 论文推荐值）

        知识点：k 参数的选择
          - k=60：标准值，对头部排名不会过于敏感
          - k 越大越平缓，k 越小越强调第一名
          - 面试考点："为什么不直接 k=0？" → 避免第一名权重过大（1/0 也无穷大）
        """
        if k <= 0:
            raise ValueError(f"Fusion k 参数必须 > 0（收到 {k}）")
        self._k = k

    def fuse(
        self,
        lists: list[list[Any]],
        top_k: int | None = None,
    ) -> list[Any]:
        """融合多路检索结果

        接口签名：fuse(lists: list[list[RetrievalResult]], top_k=None) -> list[RetrievalResult]
        入参：
          - lists: 多路检索结果列表（每个子列表是一路结果，已按自身分数降序）
            - 例如：[dense_results, sparse_results]
          - top_k: 可选，返回前 K 个结果（None 表示返回全部融合结果）
        出参：融合后的 RetrievalResult 列表，按 RRF score 降序排列

        处理流程：
          1. 计算每个文档的 RRF 分数（sum of 1/(k + rank)）
          2. 按 RRF 分数降序排列
          3. 合并文本和 metadata（取首次出现的）
          4. 更新 score 为 RRF 分数
          5. 返回 Top-K

        知识点：RRF 的复杂度
          - O(N)：N 是所有检索结果的总文档数
          - 每路结果只需遍历一次（排名已知）
          - 面试考点："RRF 的时间复杂度？" → O(N)

        面试考点：
          "多路结果有重复怎么处理？" → RRF 分数累加，重复出现得分更高
          "某路结果为空怎么办？" → 空列表不影响融合（贡献为 0）
          "为什么取首次出现的 text/metadata？" → 同一 chunk_id 的 text/metadata 相同
        """
        if not lists:
            return []

        # 计算 RRF 分数
        # rrf_scores: {chunk_id: accumulated_score}
        rrf_scores: dict[str, float] = {}
        # 保留首次出现的结果（用于获取 text/metadata）
        first_seen: dict[str, Any] = {}

        for result_list in lists:
            for rank, result in enumerate(result_list, start=1):
                chunk_id = result.chunk_id
                # RRF 分数累加
                contribution = 1.0 / (self._k + rank)
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + contribution
                # 记录首次出现的完整结果
                if chunk_id not in first_seen:
                    first_seen[chunk_id] = result

        # 按 RRF 分数降序排列（同分时按 chunk_id 字典序稳定排序）
        ranked = sorted(
            rrf_scores.items(),
            key=lambda x: (-x[1], x[0]),
        )

        # 组装最终结果
        results: list[Any] = []
        for chunk_id, rrf_score in ranked:
            original = first_seen[chunk_id]
            # 创建新结果，保留 text/metadata，更新 score 为 RRF 分数
            from core.types import RetrievalResult
            results.append(RetrievalResult(
                chunk_id=chunk_id,
                score=round(rrf_score, 6),
                text=original.text,
                metadata=dict(original.metadata),
            ))

        # Top-K 截断
        if top_k is not None and top_k > 0:
            results = results[:top_k]

        logger.debug(
            "Fusion: fused %d lists → %d unique docs → %d results (k=%d)",
            len(lists),
            len(rrf_scores),
            len(results),
            self._k,
        )

        return results

    @property
    def k(self) -> int:
        """返回 RRF 平滑常数"""
        return self._k

