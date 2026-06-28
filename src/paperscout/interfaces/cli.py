"""Command-line interface for PaperScout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, List, Optional, TextIO

from paperscout.collectors.manual import load_manual_candidates
from paperscout.ranking.scorer import RankingConfig, load_ranking_config
from paperscout.recommender.select import SelectionResult, select_best_candidate
from paperscout.storage.jsonl_store import (
    append_recommendation,
    load_profile,
    load_recommendations,
)
from paperscout.storage.schemas import (
    NO_EXTRA_CONSTRAINTS,
    PaperMetadata,
    ReaderProfile,
    RecommendationRecord,
    ScoreBreakdown,
    utc_now_iso,
)

InputFn = Callable[[str], str]

PRIMARY_FIELDS = [
    "CS-AI / machine learning methods",
    "Math + AI",
    "Chemistry + AI",
    "Biology + AI",
    "Materials + AI",
    "Physics + AI",
    "Medicine / Health + AI",
    "Economics / Finance + AI",
    "Social Science + AI",
    "Earth / Climate / Energy + AI",
    "General AI4S",
]

SUBFIELDS = {
    "CS-AI / machine learning methods": [
        "foundation models",
        "generative models",
        "reinforcement learning",
        "optimization / training",
        "interpretability / safety",
        "systems / efficiency",
    ],
    "Math + AI": [
        "theorem proving",
        "symbolic reasoning",
        "optimization",
        "probability / statistics",
        "numerical analysis",
    ],
    "Chemistry + AI": [
        "molecular property prediction",
        "generative chemistry",
        "reaction prediction",
        "molecular dynamics / force fields",
        "protein-ligand / docking",
        "lab automation",
    ],
    "Biology + AI": [
        "protein models",
        "genomics",
        "single-cell analysis",
        "biomedical foundation models",
        "drug discovery",
    ],
    "Materials + AI": [
        "materials discovery",
        "crystal generation",
        "property prediction",
        "structure relaxation",
        "simulation surrogate models",
    ],
    "Physics + AI": [
        "particle physics",
        "cosmology / astronomy",
        "fluid dynamics",
        "plasma physics",
        "physics-informed learning",
    ],
    "Medicine / Health + AI": [
        "medical imaging",
        "clinical prediction",
        "healthcare language models",
        "multi-modal diagnosis",
        "treatment planning",
    ],
    "Economics / Finance + AI": [
        "market prediction",
        "causal inference",
        "agent-based simulation",
        "economic forecasting",
        "finance risk modeling",
    ],
    "Social Science + AI": [
        "computational social science",
        "education",
        "policy analysis",
        "human behavior modeling",
        "survey / text analysis",
    ],
    "Earth / Climate / Energy + AI": [
        "weather forecasting",
        "climate modeling",
        "remote sensing",
        "energy systems",
        "carbon / sustainability",
    ],
    "General AI4S": [
        "scientific foundation models",
        "simulation surrogate models",
        "inverse design",
        "uncertainty quantification",
        "automated discovery",
    ],
}

EXPLANATION_PREFERENCES = [
    ("more_data", "多讲数据集和 benchmark"),
    ("more_experiments", "多讲实验设计和消融"),
    ("more_math", "多讲数学定义和推导"),
    ("more_reproducibility", "多讲代码和可复现性"),
    ("more_limitations", "多讲局限性和失败模式"),
    ("balanced", "平衡讲解"),
]


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "recommend":
        return run_recommend(args)

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperscout",
        description="Recommend and track high-attention AI / AI4S papers.",
    )
    subparsers = parser.add_subparsers(dest="command")

    recommend = subparsers.add_parser(
        "recommend",
        help="recommend one paper from a manual candidate file",
    )
    recommend.add_argument(
        "--candidates",
        type=Path,
        required=True,
        help="path to a manual candidate JSON file",
    )
    recommend.add_argument(
        "--ranking-config",
        type=Path,
        default=Path("configs/ranking.json"),
        help="path to ranking config JSON",
    )
    recommend.add_argument(
        "--history",
        type=Path,
        default=Path("data/history/recommendations.jsonl"),
        help="path to recommendation history JSONL",
    )
    recommend.add_argument(
        "--profile",
        type=Path,
        default=Path("data/history/profile.json"),
        help="optional reader profile JSON path",
    )
    recommend.add_argument(
        "--requirements",
        help="requirements for this run; if omitted, PaperScout asks interactively",
    )
    recommend.add_argument(
        "--report-path",
        help="optional report path to save in the recommendation record",
    )
    recommend.add_argument(
        "--record-id",
        help="optional recommendation record ID",
    )
    recommend.add_argument(
        "--show-top",
        type=int,
        default=3,
        help="number of ranked candidates to print",
    )

    return parser


def run_recommend(
    args: argparse.Namespace,
    *,
    input_fn: Optional[InputFn] = None,
    output: Optional[TextIO] = None,
) -> int:
    if input_fn is None:
        input_fn = input
    if output is None:
        output = sys.stdout
    requirements = _resolve_requirements(args.requirements, input_fn, output)
    profile = load_profile(args.profile)
    config = _load_config(args.ranking_config)
    candidates = load_manual_candidates(args.candidates)
    previous_recommendations = load_recommendations(args.history)
    result = select_best_candidate(
        candidates,
        previous_recommendations=previous_recommendations,
        config=config,
    )

    _print_context(
        requirements=requirements,
        profile=profile,
        candidate_count=len(candidates),
        previous_count=len(previous_recommendations),
        output=output,
    )
    _print_selection_result(result, show_top=args.show_top, output=output)

    if result.selected is None:
        print("没有可推荐的非重复候选论文。", file=output)
        return 1

    record = _build_recommendation_record(
        selected_paper=result.selected.paper,
        score=result.selected.score,
        requirements=requirements,
        profile=profile,
        report_path=args.report_path,
        record_id=args.record_id,
    )
    record.extra["candidate_attention"] = result.selected.candidate.attention
    record.extra["candidate_notes"] = result.selected.candidate.notes
    append_recommendation(args.history, record)

    print("", file=output)
    print(f"已保存推荐记录: {args.history}", file=output)
    print(f"record_id: {record.record_id}", file=output)
    return 0


def _resolve_requirements(
    requirements: Optional[str], input_fn: InputFn, output: TextIO
) -> str:
    if requirements is None:
        requirements = _ask_guided_requirements(input_fn, output)
    requirements = str(requirements).strip()
    return requirements or NO_EXTRA_CONSTRAINTS


def _ask_guided_requirements(input_fn: InputFn, output: TextIO) -> str:
    primary = _choose_primary_field(input_fn, output)
    subfield = None if primary is None else _choose_subfield(primary, input_fn, output)
    preferences = _choose_explanation_preferences(input_fn, output)
    free_text = input_fn("其他偏好或排除条件？没有可直接回车: ").strip()

    parts = []
    if primary:
        parts.append(f"方向: {primary}")
    if subfield:
        parts.append(f"细分方向: {subfield}")
    if preferences and preferences != ["balanced"]:
        preference_labels = _preference_labels(preferences)
        parts.append(f"讲解偏好: {', '.join(preference_labels)}")
    if free_text:
        parts.append(f"补充: {free_text}")

    return "；".join(parts) if parts else NO_EXTRA_CONSTRAINTS


def _choose_primary_field(input_fn: InputFn, output: TextIO) -> Optional[str]:
    print("请选择论文大方向：", file=output)
    for index, field_name in enumerate(PRIMARY_FIELDS, start=1):
        print(f"{index}. {field_name}", file=output)
    print(f"{len(PRIMARY_FIELDS) + 1}. 自定义 / 跳过", file=output)

    raw_choice = input_fn("输入编号，直接回车表示无额外约束: ").strip()
    if not raw_choice:
        return None
    if raw_choice == str(len(PRIMARY_FIELDS) + 1):
        custom = input_fn("请输入自定义大方向，直接回车表示跳过: ").strip()
        return custom or None
    try:
        choice = int(raw_choice)
    except ValueError:
        return raw_choice
    if 1 <= choice <= len(PRIMARY_FIELDS):
        return PRIMARY_FIELDS[choice - 1]
    return raw_choice


def _choose_subfield(
    primary: str, input_fn: InputFn, output: TextIO
) -> Optional[str]:
    subfields = SUBFIELDS.get(primary)
    if not subfields:
        return None

    print(f"请选择 `{primary}` 的细分方向：", file=output)
    for index, subfield in enumerate(subfields, start=1):
        print(f"{index}. {subfield}", file=output)
    print(f"{len(subfields) + 1}. 自定义 / 不限定", file=output)

    raw_choice = input_fn("输入编号，直接回车表示不限定: ").strip()
    if not raw_choice:
        return None
    if raw_choice == str(len(subfields) + 1):
        custom = input_fn("请输入自定义细分方向，直接回车表示不限定: ").strip()
        return custom or None
    try:
        choice = int(raw_choice)
    except ValueError:
        return raw_choice
    if 1 <= choice <= len(subfields):
        return subfields[choice - 1]
    return raw_choice


def _choose_explanation_preferences(input_fn: InputFn, output: TextIO) -> List[str]:
    print("请选择讲解偏好，可输入多个编号，用逗号分隔：", file=output)
    for index, (_, label) in enumerate(EXPLANATION_PREFERENCES, start=1):
        print(f"{index}. {label}", file=output)

    raw_choices = input_fn("直接回车表示平衡讲解: ").strip()
    if not raw_choices:
        return ["balanced"]

    selected = []
    for raw_choice in raw_choices.replace("，", ",").split(","):
        raw_choice = raw_choice.strip()
        if not raw_choice:
            continue
        try:
            choice = int(raw_choice)
        except ValueError:
            selected.append(raw_choice)
            continue
        if 1 <= choice <= len(EXPLANATION_PREFERENCES):
            selected.append(EXPLANATION_PREFERENCES[choice - 1][0])
        else:
            selected.append(raw_choice)

    return selected or ["balanced"]


def _preference_labels(preferences: List[str]) -> List[str]:
    labels_by_code = dict(EXPLANATION_PREFERENCES)
    return [labels_by_code.get(preference, preference) for preference in preferences]


def _load_config(path: Path) -> RankingConfig:
    if path.exists():
        return load_ranking_config(path)
    return RankingConfig()


def _print_context(
    *,
    requirements: str,
    profile: Optional[ReaderProfile],
    candidate_count: int,
    previous_count: int,
    output: TextIO,
) -> None:
    print(f"本次需求: {requirements}", file=output)
    if profile is None:
        print("本地偏好档案: 未找到", file=output)
    else:
        fields = ", ".join(profile.preferred_fields) or "未设置"
        print(f"本地偏好方向: {fields}", file=output)
        if profile.free_text_preference:
            print(f"偏好备注: {profile.free_text_preference}", file=output)
        print(f"讲解风格: {profile.explanation_style}", file=output)
    print(f"候选论文数: {candidate_count}", file=output)
    print(f"历史推荐数: {previous_count}", file=output)


def _print_selection_result(
    result: SelectionResult, *, show_top: int, output: TextIO
) -> None:
    print(f"跳过重复候选: {len(result.skipped_duplicates)}", file=output)
    if not result.ranked_candidates:
        return

    print("", file=output)
    print("候选排序:", file=output)
    for index, candidate in enumerate(result.ranked_candidates[:show_top], start=1):
        print(
            f"{index}. {candidate.paper.title} "
            f"(score={candidate.score.total:.3f})",
            file=output,
        )
        _print_score_breakdown(candidate.score, output=output)

    selected = result.selected
    if selected is not None:
        print("", file=output)
        print(f"推荐论文: {selected.paper.title}", file=output)
        print(f"推荐分数: {selected.score.total:.3f}", file=output)
        _print_identifier_summary(selected.paper, output=output)


def _print_score_breakdown(score: ScoreBreakdown, *, output: TextIO) -> None:
    components = ", ".join(
        f"{name}={value:.3f}" for name, value in sorted(score.components.items())
    )
    print(f"   分数拆解: {components or '无'}", file=output)
    if score.missing_signals:
        print(f"   缺失信号: {', '.join(score.missing_signals)}", file=output)
    if score.notes:
        print(f"   备注: {'; '.join(score.notes)}", file=output)


def _print_identifier_summary(paper: PaperMetadata, *, output: TextIO) -> None:
    identifiers = []
    if paper.doi:
        identifiers.append(f"DOI={paper.doi}")
    if paper.arxiv_id:
        identifiers.append(f"arXiv={paper.arxiv_id}")
    if paper.semantic_scholar_id:
        identifiers.append(f"SemanticScholar={paper.semantic_scholar_id}")
    if paper.url:
        identifiers.append(f"URL={paper.url}")
    print(f"论文标识: {', '.join(identifiers) or '缺失'}", file=output)


def _build_recommendation_record(
    *,
    selected_paper: PaperMetadata,
    score: ScoreBreakdown,
    requirements: str,
    profile: Optional[ReaderProfile],
    report_path: Optional[str],
    record_id: Optional[str],
) -> RecommendationRecord:
    return RecommendationRecord(
        paper=selected_paper,
        user_requirements=requirements,
        score=score,
        report_path=report_path,
        record_id=record_id or _default_record_id(selected_paper),
        extra={
            "profile": profile.to_dict() if profile is not None else None,
        },
    )


def _default_record_id(paper: PaperMetadata) -> str:
    identifier = "unknown"
    if paper.arxiv_id:
        identifier = f"arxiv-{paper.arxiv_id}"
    elif paper.doi:
        identifier = f"doi-{paper.doi}"
    elif paper.url:
        identifier = f"url-{paper.url}"

    safe_identifier = "".join(
        character if character.isalnum() else "-"
        for character in identifier.lower()
    ).strip("-")
    safe_timestamp = utc_now_iso().replace(":", "").replace("+", "-")
    return f"{safe_timestamp}-{safe_identifier}"
