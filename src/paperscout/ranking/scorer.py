"""Transparent scoring for manually supplied candidate attention signals."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

from paperscout.collectors.manual import ManualCandidate
from paperscout.storage.schemas import PaperMetadata, ScoreBreakdown

DEFAULT_COUNT_SIGNALS = {
    "recent_citation_count",
    "github_stars",
    "github_recent_commits",
    "video_or_talk_count",
    "blog_or_news_count",
}

DEFAULT_BOOLEAN_SIGNALS = {"paper_with_code_has_entry"}

DEFAULT_WEIGHTS = {
    "requirement_match_score": 2.0,
    "recent_citation_count": 1.0,
    "github_stars": 0.6,
    "github_recent_commits": 0.4,
    "paper_with_code_has_entry": 0.8,
    "video_or_talk_count": 0.5,
    "blog_or_news_count": 0.4,
    "source_confidence": 1.0,
}


@dataclass
class RankingConfig:
    """Weights and signal handling rules for simple candidate ranking."""

    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    count_signals: Set[str] = field(default_factory=lambda: set(DEFAULT_COUNT_SIGNALS))
    boolean_signals: Set[str] = field(
        default_factory=lambda: set(DEFAULT_BOOLEAN_SIGNALS)
    )
    missing_signal_names: Set[str] = field(default_factory=lambda: set(DEFAULT_WEIGHTS))

    def __post_init__(self) -> None:
        self.weights = {
            str(signal): float(weight) for signal, weight in self.weights.items()
        }
        self.count_signals = {str(signal) for signal in self.count_signals}
        self.boolean_signals = {str(signal) for signal in self.boolean_signals}
        self.missing_signal_names = {
            str(signal) for signal in self.missing_signal_names
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RankingConfig":
        return cls(
            weights=dict(data.get("weights") or DEFAULT_WEIGHTS),
            count_signals=set(data.get("count_signals") or DEFAULT_COUNT_SIGNALS),
            boolean_signals=set(
                data.get("boolean_signals") or DEFAULT_BOOLEAN_SIGNALS
            ),
            missing_signal_names=set(
                data.get("missing_signal_names") or data.get("weights") or DEFAULT_WEIGHTS
            ),
        )


@dataclass
class ScoredCandidate:
    """A candidate plus its auditable score breakdown."""

    paper: PaperMetadata
    candidate: ManualCandidate
    score: ScoreBreakdown


def load_ranking_config(path: Path) -> RankingConfig:
    """Load ranking config from JSON."""

    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("ranking config files currently must be JSON")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("ranking config must contain a JSON object")
    return RankingConfig.from_dict(data)


def score_candidate(
    candidate: ManualCandidate, config: Optional[RankingConfig] = None
) -> ScoredCandidate:
    """Score one manual candidate with transparent components.

    Count-like signals use `log1p(value)` so a very popular repository does not
    dominate every other signal by raw star count alone.
    """

    config = config or RankingConfig()
    components: Dict[str, float] = {}
    missing_signals: List[str] = []
    notes = list(candidate.notes)

    if "requirement_match_score" in config.weights:
        value = candidate.requirement_match_score
        components["requirement_match_score"] = (
            config.weights["requirement_match_score"] * value
        )

    for signal, weight in config.weights.items():
        if signal == "requirement_match_score":
            continue
        if signal not in candidate.attention:
            if signal in config.missing_signal_names:
                missing_signals.append(signal)
            continue
        components[signal] = weight * _coerce_signal_value(
            signal,
            candidate.attention[signal],
            count_signals=config.count_signals,
            boolean_signals=config.boolean_signals,
        )

    total = sum(components.values())
    if missing_signals:
        notes.append("some configured attention signals are missing")

    return ScoredCandidate(
        paper=candidate.paper,
        candidate=candidate,
        score=ScoreBreakdown(
            total=total,
            components=components,
            missing_signals=missing_signals,
            notes=notes,
        ),
    )


def score_candidates(
    candidates: Iterable[ManualCandidate],
    config: Optional[RankingConfig] = None,
) -> List[ScoredCandidate]:
    return [score_candidate(candidate, config=config) for candidate in candidates]


def _coerce_signal_value(
    signal: str,
    value: Any,
    *,
    count_signals: Set[str],
    boolean_signals: Set[str],
) -> float:
    if signal in boolean_signals:
        return 1.0 if _parse_bool(value, signal) else 0.0
    numeric_value = _parse_number(value, signal)
    if signal in count_signals:
        if numeric_value < 0:
            raise ValueError(f"{signal} must not be negative")
        return math.log1p(numeric_value)
    return numeric_value


def _parse_number(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


def _parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    raise ValueError(f"{field_name} must be a boolean")
