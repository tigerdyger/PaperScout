"""Generate structured paper explanation reports from prepared materials."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from paperscout.analysis.materials import MaterialChunk, PreparedMaterials

DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_MAX_SNIPPETS_PER_SECTION = 3
DEFAULT_SNIPPET_CHARS = 600

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")


@dataclass(frozen=True)
class ReportSectionPlan:
    key: str
    title: str
    purpose: str
    terms: Sequence[str]


SECTION_PLANS = [
    ReportSectionPlan(
        key="recommendation_reason",
        title="为什么推荐这篇论文",
        purpose="解释这篇论文为什么可能值得优先阅读。",
        terms=(
            "attention",
            "benchmark",
            "code",
            "dataset",
            "github",
            "performance",
            "repository",
            "state-of-the-art",
        ),
    ),
    ReportSectionPlan(
        key="one_paragraph_summary",
        title="一段话总结",
        purpose="给出只基于当前材料的抽取式概览。",
        terms=(
            "abstract",
            "contribution",
            "introduce",
            "present",
            "propose",
            "study",
            "this paper",
        ),
    ),
    ReportSectionPlan(
        key="problem_setup",
        title="问题设定",
        purpose="定位论文试图解决的问题、任务和输入输出设定。",
        terms=(
            "aim",
            "challenge",
            "goal",
            "problem",
            "setting",
            "task",
        ),
    ),
    ReportSectionPlan(
        key="core_idea",
        title="核心想法",
        purpose="抽取方法动机、核心假设、框架或关键设计。",
        terms=(
            "approach",
            "framework",
            "hypothesis",
            "idea",
            "intuition",
            "motivation",
            "propose",
        ),
    ),
    ReportSectionPlan(
        key="method_or_algorithm",
        title="方法或算法",
        purpose="定位模型结构、算法流程、训练或推理过程。",
        terms=(
            "algorithm",
            "architecture",
            "implementation",
            "inference",
            "layer",
            "method",
            "model",
            "module",
            "pipeline",
            "training",
        ),
    ),
    ReportSectionPlan(
        key="math_derivation",
        title="数学定义和推导",
        purpose="定位目标函数、损失、能量函数、概率定义或算法推导。",
        terms=(
            "algorithm",
            "definition",
            "derive",
            "energy",
            "equation",
            "gradient",
            "likelihood",
            "loss",
            "objective",
            "theorem",
        ),
    ),
    ReportSectionPlan(
        key="experimental_design",
        title="实验设计",
        purpose="抽取数据集、训练设置、评价指标和实验流程。",
        terms=(
            "benchmark",
            "dataset",
            "evaluation",
            "experiment",
            "metric",
            "test",
            "training",
            "validation",
        ),
    ),
    ReportSectionPlan(
        key="baselines_and_ablations",
        title="baseline 和消融实验",
        purpose="定位对比方法、消融实验和公平性检查。",
        terms=(
            "ablation",
            "baseline",
            "compare",
            "comparison",
            "control",
            "state-of-the-art",
            "sota",
        ),
    ),
    ReportSectionPlan(
        key="main_results",
        title="主要结果",
        purpose="抽取论文报告的核心结果和性能改善。",
        terms=(
            "accuracy",
            "achieve",
            "error",
            "improve",
            "lower",
            "outperform",
            "performance",
            "reported",
            "result",
            "reduction",
        ),
    ),
    ReportSectionPlan(
        key="limitations",
        title="局限性和可能的过度声称",
        purpose="寻找限制、失败模式、假设和未来工作线索。",
        terms=(
            "assumption",
            "cannot",
            "caveat",
            "do not",
            "fail",
            "failure",
            "future work",
            "however",
            "limitation",
            "only",
            "we leave",
        ),
    ),
    ReportSectionPlan(
        key="reproducibility",
        title="可复现性检查",
        purpose="抽取代码、数据、超参数、实现细节和可用性说明。",
        terms=(
            "available",
            "code",
            "data availability",
            "github",
            "hyperparameter",
            "implementation",
            "repository",
            "supplementary",
        ),
    ),
]


@dataclass
class EvidenceSnippet:
    chunk_id: str
    material_id: str
    kind: str
    section_name: str
    text: str
    matched_terms: List[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceSnippet":
        return cls(
            chunk_id=str(data["chunk_id"]),
            material_id=str(data["material_id"]),
            kind=str(data["kind"]),
            section_name=str(data["section_name"]),
            text=str(data.get("text") or ""),
            matched_terms=[str(term) for term in data.get("matched_terms") or []],
            score=float(data.get("score") or 0.0),
        )


@dataclass
class ExplanationSection:
    key: str
    title: str
    status: str
    body: str
    evidence: List[EvidenceSnippet] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "body": self.body,
            "evidence": [snippet.to_dict() for snippet in self.evidence],
        }


@dataclass
class ExplanationReport:
    materials: PreparedMaterials
    requirements: Optional[str]
    generated_at: str
    sections: List[ExplanationSection]
    report_path: Optional[str] = None

    def to_markdown(self) -> str:
        paper = self.materials.paper
        lines = [
            f"# {paper.title}",
            "",
            "> 生成说明：本报告由本地解析材料抽取生成，不调用外部 LLM。",
            "> 报告中的证据片段只能说明论文或 SI 中出现过相关表述；",
            "> 除非明确说明，不能视为 PaperScout 已独立核查论文结论。",
            "",
            "## 元数据",
            "",
            f"- 生成时间: `{self.generated_at}`",
            f"- 本次需求: {self.requirements or '未提供'}",
            f"- DOI: {paper.doi or '缺失'}",
            f"- arXiv ID: {paper.arxiv_id or '缺失'}",
            f"- URL: {paper.url or '缺失'}",
            "",
            "## 材料状态",
            "",
        ]
        for document in self.materials.documents:
            lines.append(
                "- "
                f"{document.kind}: {document.status}, "
                f"type={document.file_type}, "
                f"sections={len(document.sections)}, "
                f"chars={document.text_char_count}"
            )

        lines.extend(["", "## 不确定性和缺失证据", ""])
        if self.materials.issues:
            for issue in self.materials.issues:
                material = f"{issue.material_id}: " if issue.material_id else ""
                lines.append(
                    f"- {issue.severity} `{material}{issue.code}`: {issue.message}"
                )
        else:
            lines.append("- 当前材料准备阶段没有记录 warning 或 error。")

        for section in self.sections:
            lines.extend(["", f"## {section.title}", "", section.body, ""])
            if section.evidence:
                lines.append("证据片段：")
                for snippet in section.evidence:
                    terms = ", ".join(snippet.matched_terms) or "section match"
                    lines.append(
                        "- "
                        f"`{snippet.kind}/{snippet.section_name}/{snippet.chunk_id}` "
                        f"(matched: {terms})：{snippet.text}"
                    )
            else:
                lines.append("证据片段：当前解析材料中没有找到足够明确的证据。")

        lines.extend(["", "## 建议阅读顺序", ""])
        for item in suggested_reading_order(self.materials):
            lines.append(f"- {item}")

        lines.extend(["", "## 阅读时应该思考的问题", ""])
        for question in suggested_questions(self.sections):
            lines.append(f"- {question}")

        return "\n".join(lines).rstrip() + "\n"


def load_prepared_materials(path: Path) -> PreparedMaterials:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"materials file {path} must contain a JSON object")
    return PreparedMaterials.from_dict(data)


def generate_explanation_report(
    materials: PreparedMaterials,
    *,
    requirements: Optional[str] = None,
    max_snippets_per_section: int = DEFAULT_MAX_SNIPPETS_PER_SECTION,
    generated_at: Optional[str] = None,
) -> ExplanationReport:
    sections = [
        _build_explanation_section(
            plan,
            materials.chunks,
            max_snippets=max_snippets_per_section,
            requirements=requirements,
        )
        for plan in SECTION_PLANS
    ]
    return ExplanationReport(
        materials=materials,
        requirements=requirements,
        generated_at=generated_at or _utc_now(),
        sections=sections,
    )


def write_explanation_report(
    report: ExplanationReport,
    output_path: Optional[Path] = None,
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> Path:
    path = Path(output_path) if output_path is not None else default_report_path(
        report,
        reports_dir=reports_dir,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_markdown(), encoding="utf-8")
    report.report_path = str(path)
    return path


def default_report_path(
    report: ExplanationReport,
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> Path:
    date = report.generated_at.split("T", maxsplit=1)[0]
    return Path(reports_dir) / f"{date}-{_slugify(report.materials.paper.title)}.md"


def collect_evidence(
    chunks: Iterable[MaterialChunk],
    terms: Sequence[str],
    *,
    context_terms: Optional[Sequence[str]] = None,
    max_snippets: int = DEFAULT_MAX_SNIPPETS_PER_SECTION,
) -> List[EvidenceSnippet]:
    snippets = []
    for chunk in chunks:
        primary_matches = _matched_terms(chunk, terms)
        if not primary_matches:
            continue
        context_matches = _matched_terms(chunk, context_terms or [])
        matched_terms = _ordered_unique([*primary_matches, *context_matches])
        excerpt = _best_excerpt(chunk.text, matched_terms)
        if not excerpt:
            continue
        snippets.append(
            EvidenceSnippet(
                chunk_id=chunk.chunk_id,
                material_id=chunk.material_id,
                kind=chunk.kind,
                section_name=chunk.section_name,
                text=excerpt,
                matched_terms=matched_terms,
                score=_evidence_score(chunk, primary_matches)
                + 0.1 * len(context_matches),
            )
        )
    snippets.sort(
        key=lambda snippet: (
            -snippet.score,
            snippet.kind != "paper",
            snippet.section_name.lower(),
            snippet.chunk_id,
        )
    )
    return snippets[:max_snippets]


def suggested_reading_order(materials: PreparedMaterials) -> List[str]:
    section_names = {
        section.name.lower(): section.name
        for document in materials.documents
        for section in document.sections
    }
    order = []
    for preferred in (
        "abstract",
        "introduction",
        "methods",
        "methodology",
        "experiments",
        "results",
        "discussion",
        "conclusion",
        "supplementary information",
        "supporting information",
        "appendix",
    ):
        if preferred in section_names:
            order.append(section_names[preferred])
    if not order:
        order.append("先读 Abstract 或 Introduction，再读 Methods 和 Results。")
    if any(
        document.kind == "supplementary" and document.status == "parsed"
        for document in materials.documents
    ):
        order.append("最后检查 SI 中的超参数、额外实验、失败案例和实现细节。")
    return _ordered_unique(order)


def suggested_questions(sections: Sequence[ExplanationSection]) -> List[str]:
    missing = {section.title for section in sections if section.status == "missing"}
    questions = [
        "论文最核心的假设是什么？这些假设在目标应用中是否成立？",
        "实验对比是否足以支持作者声称，还是只支持较窄场景下的改进？",
        "数据集、baseline、评价指标和消融实验是否存在选择偏差？",
        "代码、数据和超参数是否足够支撑复现？",
    ]
    if missing:
        questions.append(
            "以下部分证据不足，阅读原文时需要重点核查："
            + "、".join(sorted(missing))
            + "。"
        )
    return questions


def _build_explanation_section(
    plan: ReportSectionPlan,
    chunks: Iterable[MaterialChunk],
    *,
    max_snippets: int,
    requirements: Optional[str],
) -> ExplanationSection:
    evidence = collect_evidence(
        chunks,
        plan.terms,
        context_terms=_requirement_terms(requirements),
        max_snippets=max_snippets,
    )
    if evidence:
        body = (
            f"{plan.purpose}下面列出的内容是从论文/SI 文本中抽取到的相关线索。"
            "这些线索应按“作者或材料中出现的说法”理解，后续精读时仍需核查。"
        )
        status = "evidence_found"
    else:
        body = (
            f"{plan.purpose}当前解析文本没有提供足够明确的证据。"
            "可能原因包括：PDF 抽取丢失了公式或表格、SI 未提供、章节标题识别失败，"
            "或者论文本身没有充分展开这一部分。"
        )
        status = "missing"
    return ExplanationSection(
        key=plan.key,
        title=plan.title,
        status=status,
        body=body,
        evidence=evidence,
    )


def _requirement_terms(requirements: Optional[str]) -> List[str]:
    if not requirements:
        return []
    return _ordered_unique(
        token
        for token in re.split(r"[^A-Za-z0-9_+-]+", requirements)
        if len(token) >= 4
    )


def _matched_terms(chunk: MaterialChunk, terms: Sequence[str]) -> List[str]:
    text = f"{chunk.section_name}\n{chunk.text}".lower()
    return [term for term in terms if term.lower() in text]


def _best_excerpt(text: str, matched_terms: Sequence[str]) -> str:
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_PATTERN.split(text.replace("\n", " "))
        if sentence.strip()
    ]
    if not sentences:
        return _clean_excerpt(text)

    scored = []
    for sentence in sentences:
        lower = sentence.lower()
        score = sum(1 for term in matched_terms if term.lower() in lower)
        if score:
            scored.append((score, sentence))
    if not scored:
        return _clean_excerpt(sentences[0])
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return _clean_excerpt(scored[0][1])


def _clean_excerpt(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= DEFAULT_SNIPPET_CHARS:
        return compact
    return compact[: DEFAULT_SNIPPET_CHARS - 3].rstrip() + "..."


def _evidence_score(chunk: MaterialChunk, matched_terms: Sequence[str]) -> float:
    section_boost = 1.0 if any(
        term.lower() in chunk.section_name.lower() for term in matched_terms
    ) else 0.0
    return len(matched_terms) + section_boost


def _ordered_unique(values: Iterable[str]) -> List[str]:
    unique_values = []
    seen = set()
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            unique_values.append(normalized)
            seen.add(normalized)
    return unique_values


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "paper-report"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
