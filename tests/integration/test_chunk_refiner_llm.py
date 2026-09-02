"""
ChunkRefiner LLM 集成测试 — 真实 LLM 调用验证

⚠️ 前置条件：
  - config/settings.yaml 中配置可用的 LLM（provider/model/api_key）
  - 环境变量设置对应的 API key（OPENAI_API_KEY 等）
  - 本测试会产生真实 API 调用与费用

无 API key 时自动 skip，不阻塞 CI。
"""

from __future__ import annotations

import os
import pytest
from core.settings import load_settings
from core.types import Chunk
from ingestion.transform.chunk_refiner import ChunkRefiner
from pathlib import Path


# ============================================================
# 跳过条件：无 API key 时 skip
# ============================================================

def _has_llm_api_key() -> bool:
    """检查是否有可用的 LLM API key"""
    # 尝试加载 settings.yaml，检查 api_key 是否非空
    try:
        settings = load_settings("config/settings.yaml")
        api_key = settings.llm.api_key
        if not api_key:
            return False
        # 进一步检查 provider 对应的环境变量
        provider = settings.llm.provider
        if provider in ("openai", "deepseek"):
            return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"))
        elif provider == "ollama":
            # Ollama 本地服务不需要 api_key，但需要服务运行
            import httpx
            try:
                r = httpx.get(f"{settings.llm.base_url or 'http://localhost:11434'}/api/tags", timeout=2)
                return r.status_code == 200
            except Exception:
                return False
        elif provider == "azure":
            return bool(os.environ.get("OPENAI_API_KEY"))
        return bool(api_key)
    except Exception:
        return False


# 集体 skip 装饰器：无 API key 时跳过整个文件
pytestmark = pytest.mark.skipif(
    not _has_llm_api_key(),
    reason="无可用 LLM API key（设置 OPENAI_API_KEY 或启动 Ollama 后运行此测试）",
)


# ============================================================
# 辅助函数
# ============================================================

def _make_chunk(text: str) -> Chunk:
    return Chunk(
        chunk_id="test_chunk_001",
        doc_id="doc_integration",
        text=text,
        index=0,
        source_ref="/test.md#chunk=0",
        metadata={},
    )


# ============================================================
# 集成测试
# ============================================================

class TestLLMIntegration:
    """真实 LLM 集成测试 — 验证配置正确性和 refinement 效果"""

    def test_real_llm_refinement_succeeds(self):
        """✅ 真实 LLM 调用成功，返回精炼文本"""
        settings = load_settings("config/settings.yaml")
        settings.ingestion.chunk_refiner.use_llm = True

        refiner = ChunkRefiner(settings)
        assert refiner.use_llm is True, "LLM 应该启用"

        # 含噪声的文本
        noisy_text = (
            "向量数据库 是一种   专门存储向量的系统。\n\n"
            "第 3 页\n\n"
            "支持高效的相似度检索。"
        )
        chunk = _make_chunk(noisy_text)
        result = refiner.transform([chunk])

        assert len(result) == 1
        refined = result[0]

        # 验证 LLM 被调用（refined_by="llm"）
        assert refined.metadata.get("refined_by") == "llm", (
            f"期望 refined_by='llm'，实际：{refined.metadata.get('refined_by')}"
        )

        # 验证输出非空
        assert refined.text.strip(), "精炼后文本不应为空"

        # 验证噪声被去除
        assert "第 3 页" not in refined.text, "页码噪声应被去除"

        # 验证核心内容保留
        assert "向量" in refined.text or "检索" in refined.text, (
            f"核心内容应保留，实际：{refined.text!r}"
        )

    def test_real_llm_quality_check(self):
        """✅ 输出质量验证：噪声减少、内容保留"""
        settings = load_settings("config/settings.yaml")
        settings.ingestion.chunk_refiner.use_llm = True

        refiner = ChunkRefiner(settings)

        # 多噪声文本
        noisy_text = (
            "<!-- HTML注释 -->\n\n"
            "RAG 系统的核心组件包括：  文档加载、切分、嵌入和检索。\n\n\n"
            "Page 5\n\n"
            "这些组件协同工作。"
        )
        chunk = _make_chunk(noisy_text)
        result = refiner.transform([chunk])

        refined = result[0]

        # 噪声去除
        assert "HTML注释" not in refined.text
        assert "Page 5" not in refined.text

        # 内容保留
        assert "RAG" in refined.text or "检索" in refined.text

    def test_invalid_model_degrades_gracefully(self):
        """✅ 无效模型名称时优雅降级到 rule-based"""
        settings = load_settings("config/settings.yaml")
        settings.ingestion.chunk_refiner.use_llm = True
        # 设置无效的 provider → LLM 工厂创建失败 → 降级
        settings.llm.provider = "nonexistent_provider_xyz"

        refiner = ChunkRefiner(settings)

        # 应该降级为纯规则模式
        assert refiner.use_llm is False, "无效 provider 应降级为纯规则模式"

        chunk = _make_chunk("正常文本内容。\n\nPage 3\n\n更多内容。")
        result = refiner.transform([chunk])

        # 降级后仍正常返回（规则模式）
        assert len(result) == 1
        assert result[0].metadata["refined_by"] == "rule"
        assert "Page 3" not in result[0].text
        assert "正常文本内容" in result[0].text

    def test_trace_context_records_stage(self):
        """验证 trace 上下文记录阶段数据"""
        settings = load_settings("config/settings.yaml")
        settings.ingestion.chunk_refiner.use_llm = True

        refiner = ChunkRefiner(settings)

        from core.trace.trace_context import TraceContext
        trace = TraceContext(trace_id="integration-test")

        chunk = _make_chunk("测试文本。\n\n第 2 页\n\n内容。")
        refiner.transform([chunk], trace=trace)

        stages = trace.get_stages("chunk_refiner")
        assert len(stages) == 1
        stage_data = stages[0].data
        assert stage_data["total"] == 1
        assert stage_data["use_llm"] is True

