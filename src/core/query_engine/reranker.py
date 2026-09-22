"""
Core 层 Reranker — 编排 libs.reranker 后端 + 失败 fallback

知识点：Core 层 Reranker 的职责
  - 适配层：将 Core 层 RetrievalResult 与 libs 层 RerankCandidate 互相转换
  - 降级处理：后端失败/超时时回退到 fusion 排名（fallback=True）
  - 追踪标记：记录 fallback 状态到 trace
  - 面试考点："为什么 Core 层还需要 Reranker？" → 类型转换 + 异常降级 + trace 集成

两段式检索架构（面试必问）：
  - 粗排（HybridSearch）：Dense + Sparse + RRF Fusion → 返回 Top-M 候选（召回率优先）
  - 精排（Core Reranker）：CrossEncoder / LLM Rerank → 重排返回 Top-K（精准度优先）
  - 面试考点："为什么不一步到位？" → 性能考虑，精排代价高只对少量候选执行

Fallback 策略（面试考点）：
  1. Reranker 未启用（enabled=False / backend=None）→ 返回原始排序，fallback=True
  2. Reranker 后端抛出异常 → 捕获异常，返回原始排序，fallback=True
  3. Reranker 后端超时 → 捕获异常，返回原始排序，fallback=True
  4. 面试考点："为什么 fallback 而非报错？" → 精排是锦上添花，失败不应阻塞检索

类型转换设计：
  - Core 层使用 RetrievalResult（chunk_id, score, text, metadata）
  - libs 层使用 RerankCandidate（id, score, text, metadata）
  - 转换：chunk_id ↔ id，其余字段一致

接口签名：
  CoreReranker(settings: Settings, reranker?: BaseReranker)
  rerank(query: str, candidates: list[RetrievalResult], trace?) -> list[RetrievalResult]
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from libs.reranker.base_reranker import BaseReranker

logger = logging.getLogger(__name__)


class CoreReranker:
    """Core 层 Reranker — 编排后端 + 降级处理

    知识点：CoreReranker 的设计原则
      - 单一职责：只做类型转换 + 异常降级 + trace 集成
      - 不实现具体重排逻辑（由 libs.reranker 后端实现）
      - Fail-Safe：后端失败时返回原始排序而非抛异常
      - 面试考点："Core 层和 libs 层 Reranker 的区别？" → Core 层编排+降级，libs 层算法

    接口签名：
      CoreReranker(settings, reranker=None)
      rerank(query, candidates, trace=None) -> list[RetrievalResult]
    """

    def __init__(
        self,
        settings: Settings,
        reranker: BaseReranker | None = None,
    ) -> None:
        """初始化 CoreReranker

        接口签名：CoreReranker(settings, reranker=None)
        入参：
          - settings: 全局配置（包含 rerank 设置）
          - reranker: 可选，注入 BaseReranker 实例（测试用）
        """
        self._settings = settings

        # Reranker 后端：注入 or 工厂创建
        if reranker is not None:
            self._reranker = reranker
        else:
            from libs.reranker.reranker_factory import RerankerFactory
            self._reranker = RerankerFactory.create(settings.rerank)

    def rerank(
        self,
        query: str,
        candidates: list[Any],
        trace: TraceContext | None = None,
    ) -> list[Any]:
        """精排重排序（带 fallback 降级）

        接口签名：rerank(query, candidates, trace=None) -> list[RetrievalResult]
        入参：
          - query: 用户查询文本
          - candidates: 粗排返回的候选列表（RetrievalResult）
          - trace: 可选的追踪上下文
        出参：精排后的 RetrievalResult 列表
        异常：无（后端异常被捕获，降级为原始排序）

        处理流程：
          1. 检查 Reranker 是否启用（未启用 → 返回原始排序）
          2. 检查候选是否为空（空 → 返回空列表）
          3. RetrievalResult → RerankCandidate 类型转换
          4. 调用后端 rerank()
          5. 异常处理：捕获 RerankerError 和通用 Exception
          6. RerankCandidate → RetrievalResult 类型转换
          7. 记录 trace（fallback 标记）

        面试考点：
          "Reranker 失败怎么处理？" → 捕获异常，返回原始排序，标记 fallback=True
          "为什么不抛出异常？" → 精排是锦上添花，失败不应阻塞检索流程
        """
        start = time.perf_counter()

        # 1. 检查是否启用
        if not self._settings.rerank.enabled:
            logger.debug("Reranker 已禁用，返回原始排序")
            if trace is not None:
                trace.record_stage(
                    "reranker",
                    {"status": "skipped", "reason": "disabled", "candidate_count": len(candidates)},
                    duration_ms=0.0,
                )
            return list(candidates)

        # 2. 检查候选是否为空
        if not candidates:
            return []

        # 3. RetrievalResult → RerankCandidate
        from libs.reranker.base_reranker import RerankCandidate
        rerank_candidates = [
            RerankCandidate(
                id=r.chunk_id,
                score=r.score,
                text=r.text,
                metadata=dict(r.metadata),
            )
            for r in candidates
        ]

        # 4. 调用后端 rerank（带异常降级）
        fallback = False
        try:
            ranked = self._reranker.rerank(query, rerank_candidates)
        except Exception as e:
            # 后端异常 → 降级到原始排序
            logger.warning(
                "Reranker 后端异常（fallback 到原始排序）: %s", e
            )
            ranked = rerank_candidates  # 保持 fusion 排名
            fallback = True

        # 5. RerankCandidate → RetrievalResult
        from core.types import RetrievalResult
        results = [
            RetrievalResult(
                chunk_id=c.id,
                score=c.score,
                text=c.text,
                metadata=dict(c.metadata),
            )
            for c in ranked
        ]

        # 6. 记录 trace
        duration_ms = (time.perf_counter() - start) * 1000
        if trace is not None:
            trace.record_stage(
                "reranker",
                {
                    "status": "fallback" if fallback else "success",
                    "candidate_count": len(candidates),
                    "result_count": len(results),
                    "backend": self._reranker.backend_name,
                    "fallback": fallback,
                },
                duration_ms=round(duration_ms, 2),
            )

        logger.debug(
            "CoreReranker: %d → %d (fallback=%s, %s, %.1fms)",
            len(candidates),
            len(results),
            fallback,
            self._reranker.backend_name,
            duration_ms,
        )

        return results

    @property
    def backend_name(self) -> str:
        """返回 Reranker 后端名称"""
        return self._reranker.backend_name

    @property
    def is_enabled(self) -> bool:
        """返回 Reranker 是否启用"""
        return self._settings.rerank.enabled

