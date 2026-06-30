"""LLM-enhanced paper explanation reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from paperscout.analysis.explainer import ExplanationReport
from paperscout.llm.client import LLMResponse, OpenAICompatibleClient

DEFAULT_MAX_PROMPT_CHARS = 24000


SYSTEM_PROMPT = """你是 PaperScout 的论文讲解模块。

请只基于用户提供的论文/SI 证据片段和材料状态生成中文 Markdown 报告。
你不能使用未提供的外部知识补全论文细节。

必须遵守：
- 把“论文作者声称/报告”与“已经被 PaperScout 独立核查”分开。
- 没有证据的数学推导、baseline、指标、数据集、超参数和结论必须标注缺失，不要编造。
- 对 PDF/SI 解析可能丢失公式、表格、图片和排版保持谨慎。
- 讲解重点放在问题设定、核心假设、方法结构、数学定义、实验设计、失败模式和可复现性。
- 如果材料证据太少，宁可明确说“当前材料不足以判断”，不要写完整但无依据的解释。
"""


@dataclass
class LLMExplanationResult:
    markdown: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    response_id: Optional[str] = None
    prompt_chars: int = 0


def generate_llm_explanation_report(
    extractive_report: ExplanationReport,
    client: OpenAICompatibleClient,
    *,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> LLMExplanationResult:
    messages = build_llm_explanation_messages(
        extractive_report,
        max_prompt_chars=max_prompt_chars,
    )
    response = client.create_chat_completion(messages)
    return LLMExplanationResult(
        markdown=_wrap_llm_markdown(extractive_report, response),
        model=response.model,
        usage=response.usage,
        response_id=response.response_id,
        prompt_chars=sum(len(message["content"]) for message in messages),
    )


def build_llm_explanation_messages(
    extractive_report: ExplanationReport,
    *,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> List[Mapping[str, str]]:
    if max_prompt_chars <= 0:
        raise ValueError("max_prompt_chars must be positive.")
    evidence_text = render_evidence_digest(extractive_report)
    if len(evidence_text) > max_prompt_chars:
        evidence_text = (
            evidence_text[: max_prompt_chars - 120].rstrip()
            + "\n\n[已截断：材料证据过长，请基于以上证据生成报告，并明确说明可能遗漏。]"
        )
    user_prompt = (
        "请基于下面的 PaperScout 证据摘要，生成最终中文阅读报告。\n\n"
        "报告章节必须包括：为什么推荐这篇论文、一段话总结、问题设定、核心想法、"
        "方法或算法、数学定义和推导、实验设计、baseline 和消融实验、主要结果、"
        "局限性和可能的过度声称、可复现性检查、建议阅读顺序、阅读时应该思考的问题。\n\n"
        "如果某个章节证据不足，请保留章节并写清楚证据不足原因。\n\n"
        f"{evidence_text}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def render_evidence_digest(report: ExplanationReport) -> str:
    materials = report.materials
    paper = materials.paper
    lines = [
        "# PaperScout 证据摘要",
        "",
        "## 论文元数据",
        f"- 标题: {paper.title}",
        f"- DOI: {paper.doi or '缺失'}",
        f"- arXiv ID: {paper.arxiv_id or '缺失'}",
        f"- URL: {paper.url or '缺失'}",
        f"- 用户需求: {report.requirements or '未提供'}",
        "",
        "## 材料状态",
    ]
    for document in materials.documents:
        lines.append(
            "- "
            f"{document.kind}: status={document.status}, "
            f"type={document.file_type}, "
            f"sections={len(document.sections)}, "
            f"chars={document.text_char_count}"
        )

    lines.extend(["", "## 材料准备 warning/error"])
    if materials.issues:
        for issue in materials.issues:
            material = f"{issue.material_id}: " if issue.material_id else ""
            lines.append(f"- {issue.severity} `{material}{issue.code}`: {issue.message}")
    else:
        lines.append("- 无。")

    lines.extend(["", "## 分章节证据"])
    for section in report.sections:
        lines.extend(["", f"### {section.title}", f"- 状态: {section.status}"])
        lines.append(f"- PaperScout 抽取说明: {section.body}")
        if not section.evidence:
            lines.append("- 证据: 未找到足够明确的证据。")
            continue
        lines.append("- 证据:")
        for snippet in section.evidence:
            terms = ", ".join(snippet.matched_terms) or "section match"
            lines.append(
                "  - "
                f"`{snippet.kind}/{snippet.section_name}/{snippet.chunk_id}` "
                f"(matched: {terms}): {snippet.text}"
            )
    return "\n".join(lines).rstrip() + "\n"


def _wrap_llm_markdown(
    report: ExplanationReport,
    response: LLMResponse,
) -> str:
    usage = _format_usage(response.usage)
    header = [
        f"# {report.materials.paper.title}",
        "",
        "> 生成说明：本报告由 LLM 基于 PaperScout 本地证据抽取结果生成。",
        "> 报告不代表 PaperScout 已独立核查论文结论；缺失证据必须回到原文/SI 核查。",
        f"> 模型: `{response.model}`",
    ]
    if usage:
        header.append(f"> token 用量: {usage}")
    if response.response_id:
        header.append(f"> response_id: `{response.response_id}`")
    header.extend(["", response.content.strip(), ""])
    return "\n".join(header)


def _format_usage(usage: Dict[str, Any]) -> str:
    if not usage:
        return ""
    preferred = [
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    ]
    parts = []
    for key in preferred:
        value = usage.get(key)
        if value is not None:
            parts.append(f"{key}={value}")
    for key, value in sorted(usage.items()):
        if key not in preferred and isinstance(value, (int, float, str)):
            parts.append(f"{key}={value}")
    return ", ".join(parts)
