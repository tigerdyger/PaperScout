"""Command-line interface for PaperScout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Optional, TextIO

from paperscout.analysis.explainer import (
    default_report_path,
    generate_explanation_report,
    load_prepared_materials,
    write_explanation_report,
)
from paperscout.analysis.llm_explainer import (
    build_llm_explanation_messages,
    generate_llm_explanation_report,
)
from paperscout.analysis.materials import prepare_materials
from paperscout.collectors.arxiv import search_arxiv
from paperscout.collectors.cache import HttpRequestError
from paperscout.collectors.github import (
    GitHubRepository,
    fetch_github_repository,
    search_github_repositories,
)
from paperscout.collectors.manual import (
    ManualCandidate,
    dump_manual_candidates,
    load_manual_candidates,
)
from paperscout.collectors.merge import (
    attach_github_repositories,
    collect_explicit_github_full_names,
    merge_candidate_lists,
)
from paperscout.collectors.semantic_scholar import search_semantic_scholar
from paperscout.feedback import (
    build_feedback_record,
    feedback_summary_lines,
    profile_from_feedback,
    select_recommendation_for_feedback,
)
from paperscout.llm.client import (
    LLMConfigError,
    LLMError,
    OpenAICompatibleClient,
    load_llm_config,
)
from paperscout.ranking.scorer import RankingConfig, load_ranking_config
from paperscout.recommender.select import SelectionResult, select_best_candidate
from paperscout.storage.jsonl_store import (
    append_feedback,
    append_recommendation,
    load_feedback,
    load_profile,
    load_recommendations,
    save_profile,
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
    if args.command == "collect":
        return run_collect(args)
    if args.command == "prepare-materials":
        return run_prepare_materials(args)
    if args.command == "explain":
        return run_explain(args)
    if args.command == "feedback":
        return run_feedback(args)

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

    collect = subparsers.add_parser(
        "collect",
        help="collect candidates from real metadata sources into a JSON file",
    )
    collect.add_argument(
        "--query",
        required=True,
        help="query string for metadata sources",
    )
    collect.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/candidates.generated.json"),
        help="output candidate JSON path",
    )
    collect.add_argument(
        "--source",
        action="append",
        choices=["arxiv", "semantic-scholar"],
        help="metadata source to use; can be repeated; default is arxiv",
    )
    collect.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="maximum results per paper metadata source",
    )
    collect.add_argument(
        "--refresh",
        action="store_true",
        help="ignore cached HTTP responses",
    )
    collect.add_argument(
        "--require-api-keys",
        action="store_true",
        help="require API keys for sources that support them",
    )
    collect.add_argument(
        "--github-query",
        help=(
            "optional GitHub repository search query for code attention signals; "
            "also fetches explicit repo URLs found in candidates"
        ),
    )
    collect.add_argument(
        "--github-max-results",
        type=int,
        default=5,
        help="maximum GitHub repositories to inspect when --github-query is used",
    )

    materials = subparsers.add_parser(
        "prepare-materials",
        help="parse paper PDF and optional SI into cached sections and chunks",
    )
    materials.add_argument("--title", required=True, help="paper title")
    materials.add_argument("--pdf", required=True, help="paper PDF path or URL")
    materials.add_argument("--si", help="optional SI path or URL")
    materials.add_argument("--doi", help="optional DOI")
    materials.add_argument("--arxiv-id", help="optional arXiv ID")
    materials.add_argument("--url", help="optional paper landing page URL")
    materials.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/cache/materials"),
        help="materials cache directory",
    )
    materials.add_argument(
        "--refresh",
        action="store_true",
        help="re-parse material even if parsed cache exists",
    )
    materials.add_argument(
        "--max-chunk-chars",
        type=int,
        default=1800,
        help="maximum characters per material chunk",
    )

    explain = subparsers.add_parser(
        "explain",
        help="generate a structured Markdown report from prepared materials",
    )
    explain.add_argument(
        "--materials",
        type=Path,
        required=True,
        help="prepared materials JSON path from paperscout prepare-materials",
    )
    explain.add_argument(
        "--output",
        type=Path,
        help="output Markdown path; default is reports/YYYY-MM-DD-paper-slug.md",
    )
    explain.add_argument(
        "--requirements",
        help="optional run requirements to guide evidence selection",
    )
    explain.add_argument(
        "--max-snippets",
        type=int,
        default=3,
        help="maximum evidence snippets per report section",
    )
    explain.add_argument(
        "--llm",
        action="store_true",
        help="enhance the extractive report with an OpenAI-compatible LLM",
    )
    explain.add_argument(
        "--llm-provider",
        default="siliconflow",
        help="LLM provider name; default is siliconflow",
    )
    explain.add_argument(
        "--llm-base-url",
        help="OpenAI-compatible base URL; SiliconFlow default is used if omitted",
    )
    explain.add_argument(
        "--llm-model",
        help="model name; can also be set with SILICONFLOW_MODEL",
    )
    explain.add_argument(
        "--llm-temperature",
        type=float,
        default=0.2,
        help="LLM sampling temperature",
    )
    explain.add_argument(
        "--llm-max-tokens",
        type=int,
        default=4096,
        help="maximum LLM output tokens",
    )
    explain.add_argument(
        "--llm-timeout",
        type=int,
        default=120,
        help="LLM HTTP timeout in seconds",
    )
    explain.add_argument(
        "--llm-max-prompt-chars",
        type=int,
        default=24000,
        help="maximum characters of evidence digest sent to the LLM",
    )
    explain.add_argument(
        "--save-llm-prompt",
        type=Path,
        help="optional path to save the exact LLM prompt messages for inspection",
    )

    feedback = subparsers.add_parser(
        "feedback",
        help="record reader feedback for a recommendation and update local profile",
    )
    feedback.add_argument(
        "--history",
        type=Path,
        default=Path("data/history/recommendations.jsonl"),
        help="path to recommendation history JSONL",
    )
    feedback.add_argument(
        "--feedback",
        type=Path,
        default=Path("data/history/feedback.jsonl"),
        help="path to feedback history JSONL",
    )
    feedback.add_argument(
        "--profile",
        type=Path,
        default=Path("data/history/profile.json"),
        help="path to reader profile JSON",
    )
    feedback.add_argument(
        "--record-id",
        help="recommendation record ID; default is latest recommendation",
    )
    feedback.add_argument(
        "--paper-usefulness",
        type=int,
        help="paper usefulness score from 1 to 5",
    )
    feedback.add_argument(
        "--explanation-quality",
        type=int,
        help="explanation quality score from 1 to 5",
    )
    feedback.add_argument(
        "--too-basic",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether the explanation was too basic",
    )
    feedback.add_argument(
        "--too-advanced",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether the explanation was too advanced",
    )
    feedback.add_argument(
        "--wanted-more-math",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether future explanations should include more math",
    )
    feedback.add_argument(
        "--wanted-more-experiments",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether future explanations should include more experiments",
    )
    feedback.add_argument(
        "--wanted-more-code-reproducibility",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether future explanations should include more reproducibility detail",
    )
    feedback.add_argument("--note", help="free-text feedback note")
    feedback.add_argument(
        "--skip-profile-update",
        action="store_true",
        help="save feedback without updating profile.json",
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


def run_collect(
    args: argparse.Namespace,
    *,
    output: Optional[TextIO] = None,
) -> int:
    if output is None:
        output = sys.stdout

    try:
        sources = args.source or ["arxiv"]
        collected = []
        for source in sources:
            if source == "arxiv":
                arxiv_candidates = search_arxiv(
                    args.query,
                    max_results=args.max_results,
                    refresh=args.refresh,
                )
                collected.append(arxiv_candidates)
                print(f"arXiv candidates: {len(arxiv_candidates)}", file=output)
            elif source == "semantic-scholar":
                semantic_scholar_candidates = search_semantic_scholar(
                    args.query,
                    limit=args.max_results,
                    require_api_key=args.require_api_keys,
                    refresh=args.refresh,
                )
                collected.append(semantic_scholar_candidates)
                print(
                    f"Semantic Scholar candidates: {len(semantic_scholar_candidates)}",
                    file=output,
                )
            else:
                raise ValueError(f"unsupported source: {source}")

        candidates = merge_candidate_lists(*collected)
        github_attached = 0
        if args.github_query:
            repositories = search_github_repositories(
                args.github_query,
                max_results=args.github_max_results,
                require_token=args.require_api_keys,
                refresh=args.refresh,
            )
            repositories.extend(
                _fetch_explicit_github_repositories(
                    candidates,
                    repositories,
                    require_token=args.require_api_keys,
                    refresh=args.refresh,
                    output=output,
                )
            )
            github_attached = attach_github_repositories(candidates, repositories)
            print(f"GitHub repositories considered: {len(repositories)}", file=output)
            print(f"GitHub repositories attached: {github_attached}", file=output)
    except RuntimeError as exc:
        print(f"采集失败: {exc}", file=output)
        return 1

    dump_manual_candidates(args.output, candidates)
    print(f"merged candidates: {len(candidates)}", file=output)
    print(f"wrote candidates: {args.output}", file=output)
    if args.github_query and github_attached == 0:
        print(
            "GitHub code signals were not attached because no explicit repo match "
            "was found.",
            file=output,
        )
    return 0


def run_prepare_materials(
    args: argparse.Namespace,
    *,
    output: Optional[TextIO] = None,
) -> int:
    if output is None:
        output = sys.stdout

    paper = PaperMetadata(
        title=args.title,
        doi=args.doi,
        arxiv_id=args.arxiv_id,
        url=args.url,
    )
    prepared = prepare_materials(
        paper,
        paper_pdf=args.pdf,
        supplementary=args.si,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        max_chunk_chars=args.max_chunk_chars,
    )

    print(f"materials cache: {prepared.cache_path}", file=output)
    print(f"documents: {len(prepared.documents)}", file=output)
    for document in prepared.documents:
        print(
            f"- {document.kind}: {document.status}, "
            f"type={document.file_type}, "
            f"sections={len(document.sections)}, "
            f"chars={document.text_char_count}",
            file=output,
        )
    print(f"chunks: {len(prepared.chunks)}", file=output)
    if prepared.issues:
        print("issues:", file=output)
        for issue in prepared.issues:
            material = f"{issue.material_id}: " if issue.material_id else ""
            print(
                f"- {issue.severity} {material}{issue.code}: {issue.message}",
                file=output,
            )
    return 0 if prepared.chunks else 1


def run_explain(
    args: argparse.Namespace,
    *,
    output: Optional[TextIO] = None,
) -> int:
    if output is None:
        output = sys.stdout
    if args.max_snippets <= 0:
        print("--max-snippets must be a positive integer.", file=output)
        return 1

    try:
        materials = load_prepared_materials(args.materials)
    except (OSError, ValueError) as exc:
        print(f"讲解生成失败: cannot load materials: {exc}", file=output)
        return 1

    report = generate_explanation_report(
        materials,
        requirements=args.requirements,
        max_snippets_per_section=args.max_snippets,
    )
    if getattr(args, "llm", False):
        return _run_llm_explain(args, report, output)

    report_path = write_explanation_report(report, args.output)

    missing_sections = sum(
        1 for section in report.sections if section.status == "missing"
    )
    print(f"report: {report_path}", file=output)
    print(f"sections: {len(report.sections)}", file=output)
    print(f"chunks used: {len(materials.chunks)}", file=output)
    print(f"sections missing evidence: {missing_sections}", file=output)
    return 0


def run_feedback(
    args: argparse.Namespace,
    *,
    input_fn: Optional[InputFn] = None,
    output: Optional[TextIO] = None,
) -> int:
    if input_fn is None:
        input_fn = input
    if output is None:
        output = sys.stdout

    recommendations = load_recommendations(args.history)
    try:
        recommendation = select_recommendation_for_feedback(
            recommendations,
            record_id=args.record_id,
        )
        paper_usefulness = _resolve_score(
            args.paper_usefulness,
            "论文有用程度",
            input_fn,
            output,
        )
        explanation_quality = _resolve_score(
            args.explanation_quality,
            "讲解质量",
            input_fn,
            output,
        )
        feedback_record = build_feedback_record(
            recommendation,
            paper_usefulness=paper_usefulness,
            explanation_quality=explanation_quality,
            too_basic=_resolve_optional_bool(
                args.too_basic,
                "讲解是否偏基础？",
                input_fn,
                output,
            ),
            too_advanced=_resolve_optional_bool(
                args.too_advanced,
                "讲解是否偏难？",
                input_fn,
                output,
            ),
            wanted_more_math=_resolve_optional_bool(
                args.wanted_more_math,
                "后续是否希望多讲数学定义和推导？",
                input_fn,
                output,
            ),
            wanted_more_experiments=_resolve_optional_bool(
                args.wanted_more_experiments,
                "后续是否希望多讲实验设计和消融？",
                input_fn,
                output,
            ),
            wanted_more_code_reproducibility=_resolve_optional_bool(
                args.wanted_more_code_reproducibility,
                "后续是否希望多讲代码和可复现性？",
                input_fn,
                output,
            ),
            note=_resolve_note(args.note, input_fn),
        )
    except ValueError as exc:
        print(f"反馈保存失败: {exc}", file=output)
        return 1

    append_feedback(args.feedback, feedback_record)
    print(f"已保存反馈: {args.feedback}", file=output)
    print(f"推荐记录: {recommendation.record_id or '缺失'}", file=output)
    print(f"论文: {recommendation.paper.title}", file=output)

    if args.skip_profile_update:
        return 0

    all_feedback = load_feedback(args.feedback)
    profile = profile_from_feedback(
        all_feedback,
        recommendations=recommendations,
        existing_profile=load_profile(args.profile),
    )
    save_profile(args.profile, profile)
    print(f"已更新偏好档案: {args.profile}", file=output)
    for line in feedback_summary_lines(profile):
        print(line, file=output)
    return 0


def _run_llm_explain(
    args: argparse.Namespace,
    report,
    output: TextIO,
) -> int:
    if args.llm_max_prompt_chars <= 0:
        print("--llm-max-prompt-chars must be a positive integer.", file=output)
        return 1
    try:
        config = load_llm_config(
            provider=args.llm_provider,
            base_url=args.llm_base_url,
            model=args.llm_model,
            temperature=args.llm_temperature,
            max_tokens=args.llm_max_tokens,
            timeout_seconds=args.llm_timeout,
        )
    except LLMConfigError as exc:
        print(f"LLM 配置不完整: {exc}", file=output)
        return 1

    if args.save_llm_prompt:
        messages = build_llm_explanation_messages(
            report,
            max_prompt_chars=args.llm_max_prompt_chars,
        )
        args.save_llm_prompt.parent.mkdir(parents=True, exist_ok=True)
        args.save_llm_prompt.write_text(
            json.dumps(messages, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    try:
        llm_result = generate_llm_explanation_report(
            report,
            OpenAICompatibleClient(config),
            max_prompt_chars=args.llm_max_prompt_chars,
        )
    except LLMError as exc:
        print(f"LLM 讲解生成失败: {exc}", file=output)
        return 1

    report_path = args.output or _default_llm_output_path(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(llm_result.markdown, encoding="utf-8")
    missing_sections = sum(
        1 for section in report.sections if section.status == "missing"
    )
    print(f"report: {report_path}", file=output)
    print("mode: llm", file=output)
    print(f"provider: {config.provider}", file=output)
    print(f"model: {llm_result.model}", file=output)
    print(f"prompt chars: {llm_result.prompt_chars}", file=output)
    print(f"sections: {len(report.sections)}", file=output)
    print(f"chunks used: {len(report.materials.chunks)}", file=output)
    print(f"sections missing evidence: {missing_sections}", file=output)
    return 0


def _default_llm_output_path(report) -> Path:
    extractive_path = default_report_path(report)
    return extractive_path.with_name(f"{extractive_path.stem}-llm.md")


def _fetch_explicit_github_repositories(
    candidates: List[ManualCandidate],
    repositories: List[GitHubRepository],
    *,
    require_token: bool,
    refresh: bool,
    output: TextIO,
) -> List[GitHubRepository]:
    known_full_names = {repository.full_name.lower() for repository in repositories}
    fetched = []
    for full_name in collect_explicit_github_full_names(candidates):
        if full_name.lower() in known_full_names:
            continue
        try:
            repository = fetch_github_repository(
                full_name,
                require_token=require_token,
                refresh=refresh,
            )
        except HttpRequestError as exc:
            print(
                f"GitHub repository skipped: {full_name} ({exc})",
                file=output,
            )
            continue
        fetched.append(repository)
        known_full_names.add(repository.full_name.lower())
    return fetched


def _resolve_requirements(
    requirements: Optional[str], input_fn: InputFn, output: TextIO
) -> str:
    if requirements is None:
        requirements = _ask_guided_requirements(input_fn, output)
    requirements = str(requirements).strip()
    return requirements or NO_EXTRA_CONSTRAINTS


def _resolve_score(
    score: Optional[int],
    label: str,
    input_fn: InputFn,
    output: TextIO,
) -> int:
    if score is not None:
        return _validate_cli_score(score, label)
    while True:
        try:
            raw_score = input_fn(f"{label}评分（1-5）: ").strip()
        except EOFError as exc:
            raise ValueError(f"{label}评分缺失，请传入对应命令行参数") from exc
        try:
            return _validate_cli_score(int(raw_score), label)
        except ValueError:
            print("请输入 1 到 5 之间的整数。", file=output)


def _validate_cli_score(score: int, label: str) -> int:
    score = int(score)
    if score < 1 or score > 5:
        raise ValueError(f"{label}评分必须在 1 到 5 之间")
    return score


def _resolve_optional_bool(
    value: Optional[bool],
    question: str,
    input_fn: InputFn,
    output: TextIO,
) -> bool:
    if value is not None:
        return bool(value)
    try:
        raw_value = input_fn(f"{question} [y/N]: ").strip().lower()
    except EOFError:
        return False
    if raw_value in {"", "n", "no", "0", "否", "不"}:
        return False
    if raw_value in {"y", "yes", "1", "是", "对"}:
        return True
    print("无法识别，按否处理。", file=output)
    return False


def _resolve_note(note: Optional[str], input_fn: InputFn) -> str:
    if note is not None:
        return str(note).strip()
    try:
        return input_fn("其他反馈备注？没有可直接回车: ").strip()
    except EOFError:
        return ""


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
        for line in feedback_summary_lines(profile):
            print(line, file=output)
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
