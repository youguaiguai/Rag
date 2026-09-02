"""
ChunkRefiner — Chunk 文本精炼（规则去噪 + 可选 LLM 增强 + 失败降级）

知识点：Transform 链的第一个组件
  - 职责：清洗 chunk 文本中的噪声（页眉页脚/多余空白/格式标记/HTML注释/不可见字符）
  - 增强：可选调用 LLM 智能重写（补全断裂句子、修正 OCR 错误）
  - 降级：LLM 异常时回退到规则结果，不阻塞 ingestion（Fail-Safe）

处理流程：
  chunk.text
    → _rule_based_refine()     # 第一步：规则去噪（确定性、零成本、始终执行）
    → _llm_refine()            # 第二步：LLM 增强（可选、非确定性、失败返回 None）
    → 失败降级                  # LLM 失败 → 使用规则结果 + metadata 标记 fallback 原因

降级机制设计（面试考点）：
  - 为什么要降级？→ LLM 是外部依赖（网络/API/配额），不可用不应阻塞 ingestion
  - 降级路径：LLM 异常 → 返回 None → 使用规则结果 → metadata 标记 refined_by="rule"
  - 降级标记：metadata["refined_by"] = "rule" + metadata["refinement_fallback"] = 原因
  - 对比：Fail-Fast（配置错误立即崩溃） vs Fail-Safe（数据处理降级继续）

规则去噪的代码块保护：
  - 用 ``` 分离代码块和普通文本
  - 只对普通文本应用去噪规则
  - 代码块内容原样保留（缩进/空白/符号都有语义）
  - 面试考点："为什么代码块不能去空白？" → Python 缩进有语法意义

接口签名：
  ChunkRefiner(settings: Settings, llm: BaseLLM | None = None, prompt_path: str | None = None)
  transform(chunks: list[Chunk], trace: TraceContext | None = None) -> list[Chunk]
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from ingestion.transform.base_transform import BaseTransform, TransformError
from libs.llm.base_llm import BaseLLM, LLMError
from libs.llm.llm_factory import LLMFactory
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import Settings
    from core.trace.trace_context import TraceContext
    from core.types import Chunk

logger = logging.getLogger(__name__)


# ============================================================
# 规则去噪的正则模式
# ============================================================

# 1. 不可见字符：零宽字符 + 控制字符 + Unicode 非字符（保留 \t=\x09 \n=\x0a）
#    知识点：OCR/PDF 提取常引入零宽空格（\u200b）导致向量检索匹配失败
_INVISIBLE_CHARS = re.compile(r'[\u200b\u200c\u200d\u2060\ufeff\ufffe\uffff\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# 2. HTML 注释：<!-- ... -->（多行）
_HTML_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)

# 3. 页码模式（单独成行才移除，避免误伤正文中的数字）
#    覆盖：第 3 页 / 第3页，共10页 / Page 3 / Page 3 of 10 / - 3 - / 3 / 3/10
_PAGE_NUMBER_PATTERNS = [
    re.compile(r'^[ \t]*第[ \t]*\d+[ \t]*页(?:[ \t]*[,，/][ \t]*共[ \t]*\d+[ \t]*页)?[ \t]*$', re.MULTILINE),
    re.compile(r'^[ \t]*Page[ \t]+\d+(?:[ \t]+of[ \t]+\d+)?[ \t]*$', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^[ \t]*[-–—]?[ \t]*\d+[ \t]*[-–—]?[ \t]*$', re.MULTILINE),
    re.compile(r'^[ \t]*\d+[ \t]*/[ \t]*\d+[ \t]*$', re.MULTILINE),
]

# 4. 分隔线：3+ 连续符号（- = _ * ~）
#    注意：不匹配 | 字符 → 表格分隔行 |---|---| 不会被误删
_SEPARATOR_LINE = re.compile(r'^[ \t]*[-=_*~]{3,}[ \t]*$', re.MULTILINE)

# 5. 行内连续空白 → 单空格
_MULTI_SPACE = re.compile(r'[ \t]+')

# 6. 3+ 连续换行 → 2 个换行（段落间隔）
_MULTI_NEWLINE = re.compile(r'\n{3,}')

# 7. 图片占位符（保护：[IMAGE: id] 不能被空白规则破坏）
_IMAGE_PLACEHOLDER = re.compile(r'\[IMAGE:\s*\S+?\s*\]')


# ============================================================
# ChunkRefiner — 规则去噪 + 可选 LLM 增强
# ============================================================

class ChunkRefiner(BaseTransform):
    """Chunk 文本精炼器 — 规则去噪（必有）+ LLM 增强（可选）

    知识点：两阶段清洗策略
      1. 规则阶段（确定性）：正则去噪，零成本、可重复、容易测试
      2. LLM 阶段（非确定性）：语义级清洗（断句补全/OCR 修正），有成本、需要降级
      - 顺序很重要：先规则后 LLM → LLM 拿到的是已去噪的干净文本，prompt 更短更准
      - 面试考点："为什么规则在前 LLM 在后？" → 降成本 + 确定性兜底

    接口签名：
      ChunkRefiner(settings, llm=None, prompt_path=None)
        - settings: 项目总配置（use_llm 从 settings.ingestion.chunk_refiner 读取）
        - llm: 可选注入 LLM 实例（测试用 Mock；不传则 use_llm=True 时从工厂创建）
        - prompt_path: 可选 prompt 模板路径（默认从配置读取）
    """

    # 内置 fallback prompt（prompt 文件读取失败时使用）
    # 知识点：为什么要有 fallback？→ 配置文件损坏不应导致组件不可用
    _DEFAULT_PROMPT = (
        "你是文本清洗专家。请对以下文本片段进行清洗和优化：\n"
        "1. 去除无关噪音（页眉页脚、重复文本、乱码）\n"
        "2. 补全因切分而断裂的句子\n"
        "3. 保持原文语义不变\n\n"
        "文本片段：\n{text}\n"
    )

    def __init__(
        self,
        settings: Settings,
        llm: BaseLLM | None = None,
        prompt_path: str | None = None,
    ) -> None:
        """初始化 ChunkRefiner

        接口签名：ChunkRefiner(settings, llm=None, prompt_path=None)
        入参：
          - settings: 项目总配置
          - llm: 可选注入的 LLM（依赖注入，测试传 Mock）
          - prompt_path: 可选 prompt 模板路径
        """
        self._settings = settings

        # 读取 ingestion.chunk_refiner 子配置
        refiner_cfg = settings.ingestion.chunk_refiner
        self._use_llm: bool = refiner_cfg.use_llm

        # prompt 路径优先级：构造参数 > 配置文件 > 内置默认
        self._prompt_path: str = prompt_path or refiner_cfg.prompt_path
        self._prompt_template: str = self._load_prompt(self._prompt_path)

        # LLM 实例：注入优先；未注入且 use_llm=True 时从工厂创建
        # 创建失败（配置错误/依赖缺失）→ 降级为纯规则模式（Fail-Safe）
        self._llm: BaseLLM | None = llm
        if self._use_llm and self._llm is None:
            try:
                self._llm = LLMFactory.create(settings.llm)
            except LLMError as e:
                logger.warning("ChunkRefiner: LLM 创建失败，降级为纯规则模式: %s", e)
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
        """对 chunk 列表执行规则去噪 + 可选 LLM 增强

        接口签名：transform(chunks, trace=None) -> list[Chunk]
        入参：
          - chunks: 待精炼的 Chunk 列表
          - trace: 可选追踪上下文
        出参：精炼后的 Chunk 列表（新对象，输入不可变）
        异常：TransformError — 输入整体无效

        异常隔离设计（面试考点）：
          - 单个 chunk 处理异常 → 保留原文 + metadata 标记，不影响其他 chunk
          - 只有输入整体无效（非 list）才抛异常
        """
        if not isinstance(chunks, list):
            raise TransformError(f"chunks 必须是 list，得到 {type(chunks).__name__}")

        refined: list[Chunk] = []
        for chunk in chunks:
            try:
                refined.append(self._refine_single(chunk, trace))
            except Exception as e:  # noqa: BLE001 — 降级安全：单 chunk 失败不阻塞
                logger.warning(
                    "ChunkRefiner: chunk %s 处理异常，保留原文: %s", chunk.chunk_id, e
                )
                fallback_meta = dict(chunk.metadata)
                fallback_meta["refined_by"] = "error"
                fallback_meta["refinement_fallback"] = f"exception: {e}"
                refined.append(replace(chunk, metadata=fallback_meta))

        # 记录阶段数据（trace 可选）
        if trace is not None:
            trace.record_stage(
                "chunk_refiner",
                {
                    "total": len(refined),
                    "refined_by_llm": sum(
                        1 for c in refined if c.metadata.get("refined_by") == "llm"
                    ),
                    "refined_by_rule": sum(
                        1 for c in refined if c.metadata.get("refined_by") == "rule"
                    ),
                    "use_llm": self._use_llm,
                },
            )

        return refined

    # --------------------------------------------------------
    # 单 chunk 处理
    # --------------------------------------------------------

    def _refine_single(self, chunk: Chunk, trace: TraceContext | None) -> Chunk:
        """处理单个 chunk：规则去噪 → 可选 LLM 增强 → 降级

        接口签名：_refine_single(chunk, trace) -> Chunk
        处理流程：
          1. rule_result = _rule_based_refine(chunk.text)
          2. use_llm=False → 直接用 rule_result，refined_by="rule"
          3. use_llm=True → llm_result = _llm_refine(rule_result)
             - 成功：用 llm_result，refined_by="llm"
             - 失败：用 rule_result，refined_by="rule" + fallback 原因
        """
        # 第一步：规则去噪（始终执行，确定性兜底）
        rule_result = self._rule_based_refine(chunk.text)

        # Fail-Safe：规则清理后为空（如整个 chunk 都是页码）→ 保留原文
        if not rule_result:
            rule_result = chunk.text

        new_metadata = dict(chunk.metadata)

        if not self._use_llm or self._llm is None:
            # 纯规则模式
            new_metadata["refined_by"] = "rule"
            return replace(chunk, text=rule_result, metadata=new_metadata)

        # 第二步：LLM 增强（可选）
        llm_result, fallback_reason = self._llm_refine(rule_result, trace)

        if llm_result is not None:
            new_metadata["refined_by"] = "llm"
            return replace(chunk, text=llm_result, metadata=new_metadata)

        # 降级：LLM 失败 → 使用规则结果 + 标记原因
        new_metadata["refined_by"] = "rule"
        new_metadata["refinement_fallback"] = fallback_reason or "llm_unavailable"
        return replace(chunk, text=rule_result, metadata=new_metadata)

    # --------------------------------------------------------
    # 规则去噪
    # --------------------------------------------------------

    def _rule_based_refine(self, text: str) -> str:
        """规则去噪 — 确定性文本清洗

        接口签名：_rule_based_refine(text: str) -> str
        入参：原始文本
        出参：去噪后的文本

        清洗规则：
          1. 去除不可见字符（零宽空格/控制字符）
          2. 去除 HTML 注释 <!-- -->
          3. 去除页码行（第X页 / Page X / - X - / X/Y）
          4. 去除分隔线行（--- / === / ***，3+ 符号）
          5. 行内连续空白合并为单空格，行首尾 strip
          6. 3+ 连续换行合并为 2 个
        保护规则：
          - 代码块（``` 包裹）内部内容原样保留
          - 图片占位符 [IMAGE: id] 不受空白规则影响（占位符内部空格已由正则保护）
        """
        if not text:
            return text

        # 代码块保护：按 ``` 分离，奇数部分是代码内容
        parts = text.split("```")
        cleaned_parts: list[str] = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                cleaned_parts.append(self._clean_text_segment(part))
            else:
                cleaned_parts.append(part)  # 代码块原样保留
        return "```".join(cleaned_parts)

    def _clean_text_segment(self, text: str) -> str:
        """对非代码块文本段应用清洗规则

        接口签名：_clean_text_segment(text: str) -> str
        知识点：规则顺序很重要
          - 先去注释/页码（行级删除），再合并空白（字符级）
          - 如果先合并空白，页码正则的行锚定 ^$ 可能失效
        """
        if not text:
            return text

        # 1. 不可见字符
        text = _INVISIBLE_CHARS.sub('', text)

        # 2. HTML 注释
        text = _HTML_COMMENT.sub('', text)

        # 3. 页码行（逐个模式匹配）
        for pattern in _PAGE_NUMBER_PATTERNS:
            text = pattern.sub('', text)

        # 4. 分隔线行
        text = _SEPARATOR_LINE.sub('', text)

        # 5. 行内空白合并 + 行首尾 strip（逐行处理）
        lines = [_MULTI_SPACE.sub(' ', line).strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        # 6. 多换行合并（3+ → 2）
        text = _MULTI_NEWLINE.sub('\n\n', text)

        # 7. 整体首尾 strip
        return text.strip()

    # --------------------------------------------------------
    # LLM 增强
    # --------------------------------------------------------

    def _llm_refine(
        self, text: str, trace: TraceContext | None = None
    ) -> tuple[str | None, str | None]:
        """LLM 智能增强（可选，失败安全）

        接口签名：_llm_refine(text, trace) -> (refined | None, fallback_reason | None)
        入参：
          - text: 规则去噪后的文本
          - trace: 可选追踪上下文
        出参：
          - refined: LLM 重写结果；失败返回 None
          - fallback_reason: 失败原因（成功时为 None）

        失败场景（面试考点："LLM 什么时候触发降级？"）：
          1. LLMError — 网络/认证/限流异常
          2. 空响应 — LLM 返回空字符串或纯空白
          3. 意外异常 — 兜底捕获
        """
        if not text:
            return None, "empty_input"

        # 填充 prompt 模板（用 replace 而非 format，避免模板中其他 {} 干扰）
        prompt = self._prompt_template.replace("{text}", text)

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": "你是文本清洗专家，只输出清洗后的文本。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = self._llm.chat(messages)  # type: ignore[union-attr] — 调用前已确保非 None
        except LLMError as e:
            reason = f"llm_error: {e}"
            logger.warning("ChunkRefiner: LLM 调用失败，降级到规则结果: %s", e)
            if trace is not None:
                trace.record_stage("chunk_refiner.llm_error", {"reason": reason})
            return None, reason
        except Exception as e:  # noqa: BLE001 — 意外异常也要降级
            reason = f"llm_unexpected_error: {e}"
            logger.warning("ChunkRefiner: LLM 调用出现意外异常，降级: %s", e)
            if trace is not None:
                trace.record_stage("chunk_refiner.llm_error", {"reason": reason})
            return None, reason

        # 空响应检查（LLM 返回空 → 视为失败）
        if not response or not response.strip():
            reason = "llm_empty_response"
            if trace is not None:
                trace.record_stage("chunk_refiner.llm_error", {"reason": reason})
            return None, reason

        return response.strip(), None

    # --------------------------------------------------------
    # Prompt 加载
    # --------------------------------------------------------

    def _load_prompt(self, prompt_path: str | None = None) -> str:
        """从文件加载 prompt 模板（支持默认 fallback）

        接口签名：_load_prompt(prompt_path: str | None = None) -> str
        入参：prompt 文件路径（可选）
        出参：prompt 模板字符串（包含 {text} 占位符）

        加载优先级：指定路径 > 内置默认
        知识点：为什么文件读取失败不抛异常？
          - prompt 是"增强配置"，不是"核心依赖"
          - 文件损坏/缺失 → 用内置默认 prompt，组件仍可用（Fail-Safe）
          - 面试考点："配置缺失的三种策略" → Fail-Fast / 默认值 / 降级
        """
        if prompt_path:
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    return content
                logger.warning("ChunkRefiner: prompt 文件为空: %s，使用内置默认", prompt_path)
            except OSError as e:
                logger.warning(
                    "ChunkRefiner: prompt 文件读取失败: %s (%s)，使用内置默认",
                    prompt_path, e,
                )
        return self._DEFAULT_PROMPT

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def use_llm(self) -> bool:
        """是否启用 LLM 增强（降级后可能为 False）"""
        return self._use_llm

    @property
    def prompt_template(self) -> str:
        """当前使用的 prompt 模板"""
        return self._prompt_template

