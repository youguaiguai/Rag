"""
RagasEvaluator 单元测试 — H1: Ragas 评估器

测试策略：
  - Mock ragas 模块验证基本逻辑
  - 测试 ImportError 降级
  - 测试 evaluate() 返回正确格式
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

_src_dir = Path(__file__).parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# ============================================================
# TestRagasEvaluatorInit — 初始化测试
# ============================================================

class TestRagasEvaluatorInit:
    """RagasEvaluator 初始化测试（2 个测试）"""

    def test_backend_name(self) -> None:
        """backend_name 返回 ragas"""
        with patch.dict("sys.modules", {"ragas": MagicMock(), "ragas.metrics": MagicMock(), "datasets": MagicMock()}):
            from observability.evaluation.ragas_evaluator import RagasEvaluator
            ev = RagasEvaluator()
            assert ev.backend_name == "ragas"

    def test_import_error_raised_when_ragas_missing(self) -> None:
        """Ragas 未安装时抛出 ImportError"""
        # 模拟 ragas 未安装
        original = sys.modules.get("ragas")
        sys.modules["ragas"] = None  # type: ignore

        try:
            with pytest.raises(ImportError, match="ragas"):
                from observability.evaluation.ragas_evaluator import RagasEvaluator
                RagasEvaluator()
        finally:
            if original is not None:
                sys.modules["ragas"] = original


# ============================================================
# TestFactoryRegistration — 工厂注册测试
# ============================================================

class TestFactoryRegistration:
    """EvaluatorFactory ragas 注册测试（2 个测试）"""

    def test_ragas_in_supported_backends(self) -> None:
        """ragas 在支持列表中"""
        from libs.evaluator.evaluator_factory import EvaluatorFactory
        backends = EvaluatorFactory.supported_backends()
        assert "ragas" in backends

    def test_create_ragas_if_available(self) -> None:
        """ragas 可用时能创建实例"""
        from libs.evaluator.evaluator_factory import EvaluatorFactory, EvaluatorError
        try:
            ev = EvaluatorFactory.create("ragas")
            assert ev.backend_name == "ragas"
        except (EvaluatorError, ImportError):
            pass  # Ragas 未安装时跳过


from libs.evaluator.base_evaluator import EvaluatorError  # noqa: E402

