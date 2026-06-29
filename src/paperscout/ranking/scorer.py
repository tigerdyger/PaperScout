"""Transparent scoring for candidate attention signals."""

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
    "github_forks",
    "github_recent_commits",
    "video_or_talk_count",
    "blog_or_news_count",
    "semantic_scholar_citation_count",
    "semantic_scholar_influential_citation_count",
}

DEFAULT_BOOLEAN_SIGNALS = {"github_repository_present", "paper_with_code_has_entry"}

DEFAULT_BOUNDED_SIGNALS = {"source_confidence"}

DEFAULT_GROUP_WEIGHTS = {
    "requirement_match_score": 1.0,
    "recent_attention_score": 2.0,
    "reproducibility_signal_score": 1.0,
    "lifetime_attention_score": 0.5,
    "source_confidence_score": 0.8,
    "low_confidence_penalty": 0.5,
}

DEFAULT_SIGNAL_GROUPS = {
    "recent_attention_score": {
        "recent_citation_count": 1.0,
        "github_recent_commits": 0.7,
        "video_or_talk_count": 0.5,
        "blog_or_news_count": 0.5,
    },
    "reproducibility_signal_score": {
        "paper_with_code_has_entry": 1.0,
        "github_repository_present": 0.8,
    },
    "lifetime_attention_score": {
        "github_stars": 0.7,
        "github_forks": 0.3,
        "semantic_scholar_citation_count": 0.5,
        "semantic_scholar_influential_citation_count": 0.7,
    },
    "source_confidence_score": {
        "source_confidence": 1.0,
    },
}

DEFAULT_COUNT_REFERENCE_VALUES = {
    "recent_citation_count": 25.0,
    "github_recent_commits": 20.0,
    "video_or_talk_count": 5.0,
    "blog_or_news_count": 5.0,
    "github_stars": 500.0,
    "github_forks": 50.0,
    "semantic_scholar_citation_count": 500.0,
    "semantic_scholar_influential_citation_count": 50.0,
}

DEFAULT_MISSING_SIGNAL_NAMES = {
    signal
    for signal_group in DEFAULT_SIGNAL_GROUPS.values()
    for signal in signal_group
    if signal != "github_repository_present"
}


@dataclass
class RankingConfig:
    """Weights and signal handling rules for grouped candidate ranking."""

    group_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_GROUP_WEIGHTS)
    )
    signal_groups: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: _copy_nested_float_mapping(DEFAULT_SIGNAL_GROUPS)
    )
    count_reference_values: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_COUNT_REFERENCE_VALUES)
    )
    count_signals: Set[str] = field(default_factory=lambda: set(DEFAULT_COUNT_SIGNALS))
    boolean_signals: Set[str] = field(
        default_factory=lambda: set(DEFAULT_BOOLEAN_SIGNALS)
    )
    bounded_signals: Set[str] = field(default_factory=lambda: set(DEFAULT_BOUNDED_SIGNALS))
    missing_signal_names: Set[str] = field(
        default_factory=lambda: set(DEFAULT_MISSING_SIGNAL_NAMES)
    )
    low_confidence_threshold: float = 0.5

    def __post_init__(self) -> None:
        self.group_weights = {
            str(group): float(weight) for group, weight in self.group_weights.items()
        }
        self.signal_groups = {
            str(group): {
                str(signal): float(weight)
                for signal, weight in dict(signals).items()
            }
            for group, signals in self.signal_groups.items()
        }
        self.count_reference_values = {
            str(signal): float(value)
            for signal, value in self.count_reference_values.items()
        }
        self.count_signals = {str(signal) for signal in self.count_signals}
        self.boolean_signals = {str(signal) for signal in self.boolean_signals}
        self.bounded_signals = {str(signal) for signal in self.bounded_signals}
        self.missing_signal_names = {
            str(signal) for signal in self.missing_signal_names
        }
        self.low_confidence_threshold = float(self.low_confidence_threshold)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RankingConfig":
        return cls(
            group_weights=dict(data.get("group_weights") or DEFAULT_GROUP_WEIGHTS),
            signal_groups=_nested_mapping(
                data.get("signal_groups") or DEFAULT_SIGNAL_GROUPS
            ),
            count_reference_values=dict(
                data.get("count_reference_values") or DEFAULT_COUNT_REFERENCE_VALUES
            ),
            count_signals=set(data.get("count_signals") or DEFAULT_COUNT_SIGNALS),
            boolean_signals=set(
                data.get("boolean_signals") or DEFAULT_BOOLEAN_SIGNALS
            ),
            bounded_signals=set(data.get("bounded_signals") or DEFAULT_BOUNDED_SIGNALS),
            missing_signal_names=set(
                data.get("missing_signal_names") or DEFAULT_MISSING_SIGNAL_NAMES
            ),
            low_confidence_threshold=float(
                data.get("low_confidence_threshold", 0.5)
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
    """Score one candidate with transparent grouped components.

    Count-like signals use bounded `log1p(value) / log1p(reference)`.
    Missing signals add no evidence and are reported separately.
    """

    config = config or RankingConfig()
    components: Dict[str, float] = {}
    missing_signals: List[str] = []
    notes = list(candidate.notes)
    attention = _attention_with_derived_signals(candidate)

    if "requirement_match_score" in config.group_weights:
        components["requirement_match_score"] = (
            config.group_weights["requirement_match_score"]
            * candidate.requirement_match_score
        )

    for group_name, signal_weights in config.signal_groups.items():
        group_value = _score_signal_group(
            signal_weights,
            attention,
            config=config,
            missing_signals=missing_signals,
        )
        group_weight = config.group_weights.get(group_name, 0.0)
        components[group_name] = group_weight * group_value

    low_confidence_penalty = _low_confidence_penalty(attention, config)
    if low_confidence_penalty:
        components["low_confidence_penalty"] = low_confidence_penalty

    total = sum(components.values())
    if missing_signals:
        notes.append(
            "some configured attention signals are missing; missing signals add no "
            "positive evidence"
        )

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
    config: RankingConfig,
) -> float:
    if signal in config.boolean_signals:
        return 1.0 if _parse_bool(value, signal) else 0.0
    numeric_value = _parse_number(value, signal)
    if signal in config.count_signals:
        if numeric_value < 0:
            raise ValueError(f"{signal} must not be negative")
        reference_value = config.count_reference_values.get(signal, 1.0)
        if reference_value <= 0:
            raise ValueError(f"{signal} reference value must be positive")
        return min(1.0, math.log1p(numeric_value) / math.log1p(reference_value))
    if signal in config.bounded_signals:
        return max(0.0, min(1.0, numeric_value))
    return numeric_value


def _score_signal_group(
    signal_weights: Mapping[str, float],
    attention: Mapping[str, Any],
    *,
    config: RankingConfig,
    missing_signals: List[str],
) -> float:
    weighted_sum = 0.0
    total_weight = sum(abs(float(weight)) for weight in signal_weights.values())
    if total_weight == 0:
        return 0.0

    for signal, weight in signal_weights.items():
        if signal not in attention:
            if signal in config.missing_signal_names:
                missing_signals.append(signal)
            continue
        weighted_sum += float(weight) * _coerce_signal_value(
            signal,
            attention[signal],
            config=config,
        )
    return weighted_sum / total_weight


def _attention_with_derived_signals(candidate: ManualCandidate) -> Dict[str, Any]:
    attention = dict(candidate.attention)
    if "github_repository_present" not in attention:
        attention["github_repository_present"] = _has_github_metadata(candidate)
    return attention


def _has_github_metadata(candidate: ManualCandidate) -> bool:
    github_attention_keys = {
        "github_forks",
        "github_open_issues",
        "github_pushed_at",
        "github_stars",
    }
    if any(key in candidate.attention for key in github_attention_keys):
        return True

    github_extra_keys = {
        "github_full_name",
        "github_repository",
        "github_url",
        "github_urls",
    }
    return any(key in candidate.paper.extra for key in github_extra_keys)


def _low_confidence_penalty(
    attention: Mapping[str, Any], config: RankingConfig
) -> float:
    if "source_confidence" not in attention:
        return 0.0
    confidence = _coerce_signal_value(
        "source_confidence",
        attention["source_confidence"],
        config=config,
    )
    gap = max(0.0, config.low_confidence_threshold - confidence)
    return -config.group_weights.get("low_confidence_penalty", 0.0) * gap


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


def _copy_nested_float_mapping(
    value: Mapping[str, Mapping[str, float]]
) -> Dict[str, Dict[str, float]]:
    return {
        str(group): {
            str(signal): float(weight)
            for signal, weight in dict(signals).items()
        }
        for group, signals in value.items()
    }


def _nested_mapping(value: Any) -> Dict[str, Dict[str, float]]:
    if not isinstance(value, Mapping):
        raise ValueError("signal_groups must be an object")
    return {
        str(group): {
            str(signal): float(weight)
            for signal, weight in dict(signals).items()
        }
        for group, signals in value.items()
    }
