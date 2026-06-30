"""Build lightweight reader preferences from feedback records."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence

from paperscout.storage.schemas import (
    DEFAULT_EXPLANATION_STYLE,
    FeedbackRecord,
    ReaderProfile,
    RecommendationRecord,
)

HIGH_USEFULNESS_THRESHOLD = 4
TAG_LABELS = {
    "too_basic": "讲解偏基础",
    "too_advanced": "讲解偏难",
    "wanted_more_math": "多讲数学定义和推导",
    "wanted_more_experiments": "多讲实验设计和消融",
    "wanted_more_code_reproducibility": "多讲代码和可复现性",
}
TAG_ORDER = {tag: index for index, tag in enumerate(TAG_LABELS)}


@dataclass(frozen=True)
class FeedbackSummary:
    total_count: int
    average_paper_usefulness: float
    average_explanation_quality: float
    tag_counts: Dict[str, int] = field(default_factory=dict)
    preferred_fields: List[str] = field(default_factory=list)
    explanation_style: str = DEFAULT_EXPLANATION_STYLE
    preference_hint: str = ""
    last_feedback_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "average_paper_usefulness": self.average_paper_usefulness,
            "average_explanation_quality": self.average_explanation_quality,
            "tag_counts": self.tag_counts,
            "preferred_fields": self.preferred_fields,
            "explanation_style": self.explanation_style,
            "preference_hint": self.preference_hint,
            "last_feedback_at": self.last_feedback_at,
        }


def build_feedback_record(
    recommendation: RecommendationRecord,
    *,
    paper_usefulness: int,
    explanation_quality: int,
    too_basic: bool = False,
    too_advanced: bool = False,
    wanted_more_math: bool = False,
    wanted_more_experiments: bool = False,
    wanted_more_code_reproducibility: bool = False,
    note: str = "",
) -> FeedbackRecord:
    return FeedbackRecord(
        paper_usefulness=paper_usefulness,
        explanation_quality=explanation_quality,
        recommendation_id=recommendation.record_id,
        paper_identifiers=sorted(recommendation.paper.identifier_keys()),
        paper_title=recommendation.paper.title,
        too_basic=too_basic,
        too_advanced=too_advanced,
        wanted_more_math=wanted_more_math,
        wanted_more_experiments=wanted_more_experiments,
        wanted_more_code_reproducibility=wanted_more_code_reproducibility,
        note=note,
    )


def select_recommendation_for_feedback(
    recommendations: Sequence[RecommendationRecord],
    *,
    record_id: Optional[str] = None,
) -> RecommendationRecord:
    if not recommendations:
        raise ValueError("recommendation history is empty")
    if record_id:
        for recommendation in recommendations:
            if recommendation.record_id == record_id:
                return recommendation
        raise ValueError(f"recommendation record not found: {record_id}")
    return recommendations[-1]


def summarize_feedback(
    feedback_records: Sequence[FeedbackRecord],
    *,
    recommendations: Sequence[RecommendationRecord] = (),
) -> FeedbackSummary:
    if not feedback_records:
        return FeedbackSummary(
            total_count=0,
            average_paper_usefulness=0.0,
            average_explanation_quality=0.0,
        )

    tag_counts = Counter()
    for record in feedback_records:
        for tag in TAG_LABELS:
            if getattr(record, tag):
                tag_counts[tag] += 1

    preferred_fields = _preferred_fields_from_feedback(
        feedback_records,
        recommendations,
    )
    explanation_style = _infer_explanation_style(tag_counts)
    hint = _build_preference_hint(feedback_records, tag_counts, explanation_style)
    return FeedbackSummary(
        total_count=len(feedback_records),
        average_paper_usefulness=round(
            mean(record.paper_usefulness for record in feedback_records),
            2,
        ),
        average_explanation_quality=round(
            mean(record.explanation_quality for record in feedback_records),
            2,
        ),
        tag_counts=dict(sorted(tag_counts.items())),
        preferred_fields=preferred_fields,
        explanation_style=explanation_style,
        preference_hint=hint,
        last_feedback_at=max(record.feedback_at for record in feedback_records),
    )


def profile_from_feedback(
    feedback_records: Sequence[FeedbackRecord],
    *,
    recommendations: Sequence[RecommendationRecord] = (),
    existing_profile: Optional[ReaderProfile] = None,
) -> ReaderProfile:
    summary = summarize_feedback(
        feedback_records,
        recommendations=recommendations,
    )
    if existing_profile is None:
        existing_profile = ReaderProfile()

    preferred_fields = summary.preferred_fields or existing_profile.preferred_fields
    explanation_style = (
        summary.explanation_style
        if summary.total_count
        else existing_profile.explanation_style
    )
    free_text_preference = (
        summary.preference_hint
        if summary.preference_hint
        else existing_profile.free_text_preference
    )
    extra = dict(existing_profile.extra)
    extra["feedback_summary"] = summary.to_dict()
    return ReaderProfile(
        preferred_fields=preferred_fields,
        free_text_preference=free_text_preference,
        explanation_style=explanation_style,
        extra=extra,
    )


def feedback_summary_lines(profile: Optional[ReaderProfile]) -> List[str]:
    if profile is None:
        return []
    summary = profile.extra.get("feedback_summary")
    if not isinstance(summary, dict):
        return []
    total_count = int(summary.get("total_count") or 0)
    if total_count <= 0:
        return []
    usefulness = summary.get("average_paper_usefulness")
    quality = summary.get("average_explanation_quality")
    hint = str(summary.get("preference_hint") or "").strip()
    lines = [
        f"反馈样本: {total_count} 条，平均论文有用度 {usefulness}/5，讲解质量 {quality}/5"
    ]
    if hint:
        lines.append(f"反馈提示: {hint}")
    return lines


def _preferred_fields_from_feedback(
    feedback_records: Sequence[FeedbackRecord],
    recommendations: Sequence[RecommendationRecord],
) -> List[str]:
    recommendations_by_id = {
        recommendation.record_id: recommendation for recommendation in recommendations
    }
    field_counts = Counter()
    for feedback in feedback_records:
        if feedback.paper_usefulness < HIGH_USEFULNESS_THRESHOLD:
            continue
        recommendation = recommendations_by_id.get(feedback.recommendation_id)
        if recommendation is None:
            continue
        field = _extract_field(recommendation.user_requirements)
        if field:
            field_counts[field] += 1
    return [
        field
        for field, _ in sorted(
            field_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]
    ]


def _extract_field(requirements: str) -> Optional[str]:
    match = re.search(r"方向:\s*([^；;]+)", requirements or "")
    if not match:
        return None
    field = match.group(1).strip()
    return field or None


def _infer_explanation_style(tag_counts: Counter) -> str:
    style_counts = {
        "more_math": tag_counts["wanted_more_math"],
        "more_experiments": tag_counts["wanted_more_experiments"],
        "more_reproducibility": tag_counts["wanted_more_code_reproducibility"],
    }
    best_count = max(style_counts.values())
    if best_count <= 0:
        return DEFAULT_EXPLANATION_STYLE
    winners = [
        style
        for style, count in style_counts.items()
        if count == best_count
    ]
    return winners[0] if len(winners) == 1 else DEFAULT_EXPLANATION_STYLE


def _build_preference_hint(
    feedback_records: Sequence[FeedbackRecord],
    tag_counts: Counter,
    explanation_style: str,
) -> str:
    parts = []
    labels = [
        TAG_LABELS[tag]
        for tag, count in sorted(
            tag_counts.items(),
            key=lambda item: (-item[1], TAG_ORDER[item[0]]),
        )
        if count > 0
    ][:3]
    if labels:
        parts.append("后续讲解倾向: " + "、".join(labels))
    if explanation_style != DEFAULT_EXPLANATION_STYLE:
        parts.append(f"建议讲解风格: {explanation_style}")
    recent_notes = [record.note for record in feedback_records[-3:] if record.note]
    if recent_notes:
        parts.append("近期备注: " + " / ".join(recent_notes))
    return "；".join(parts)
