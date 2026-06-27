"""Recommendation selection helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from paperscout.collectors.manual import ManualCandidate
from paperscout.ranking.scorer import RankingConfig, ScoredCandidate, score_candidates
from paperscout.storage.jsonl_store import has_recommended_paper
from paperscout.storage.schemas import RecommendationRecord


@dataclass
class SelectionResult:
    """Result of ranking candidates after history-based duplicate filtering."""

    selected: Optional[ScoredCandidate]
    ranked_candidates: List[ScoredCandidate] = field(default_factory=list)
    skipped_duplicates: List[ManualCandidate] = field(default_factory=list)


def select_best_candidate(
    candidates: Iterable[ManualCandidate],
    previous_recommendations: Iterable[RecommendationRecord],
    config: Optional[RankingConfig] = None,
) -> SelectionResult:
    """Select the highest-scoring candidate not found in recommendation history."""

    previous_recommendations = list(previous_recommendations)
    available_candidates: List[ManualCandidate] = []
    skipped_duplicates: List[ManualCandidate] = []

    for candidate in candidates:
        if has_recommended_paper(candidate.paper, previous_recommendations):
            skipped_duplicates.append(candidate)
        else:
            available_candidates.append(candidate)

    ranked_candidates = sorted(
        score_candidates(available_candidates, config=config),
        key=lambda candidate: (-candidate.score.total, candidate.paper.title.lower()),
    )
    selected = ranked_candidates[0] if ranked_candidates else None

    return SelectionResult(
        selected=selected,
        ranked_candidates=ranked_candidates,
        skipped_duplicates=skipped_duplicates,
    )
