"""Data structures for local PaperScout history.

The storage layer intentionally uses small standard-library dataclasses. This
keeps early records easy to inspect, diff, and migrate before the project has
enough real usage to justify a database or heavier schema library.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set
from urllib.parse import urlsplit, urlunsplit

NO_EXTRA_CONSTRAINTS = "no_extra_constraints"
DEFAULT_EXPLANATION_STYLE = "balanced"


def utc_now_iso() -> str:
    """Return a compact UTC timestamp for local history records."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _string_list(values: Optional[Iterable[Any]]) -> List[str]:
    if values is None:
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Normalize a DOI without trying to validate publisher-specific syntax."""

    value = _clean_optional_text(doi)
    if value is None:
        return None
    value = value.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value.strip() or None


def normalize_arxiv_id(arxiv_id: Optional[str]) -> Optional[str]:
    """Normalize common arXiv ID forms such as URLs, PDF URLs, and arXiv: IDs."""

    value = _clean_optional_text(arxiv_id)
    if value is None:
        return None

    lower_value = value.lower()
    for prefix in (
        "arxiv:",
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://arxiv.org/pdf/",
        "http://arxiv.org/pdf/",
    ):
        if lower_value.startswith(prefix):
            value = value[len(prefix) :]
            break

    if value.lower().endswith(".pdf"):
        value = value[:-4]
    return value.strip().lower() or None


def normalize_semantic_scholar_id(paper_id: Optional[str]) -> Optional[str]:
    value = _clean_optional_text(paper_id)
    return value.lower() if value is not None else None


def canonicalize_url(url: Optional[str]) -> Optional[str]:
    """Normalize URLs enough for local duplicate checks.

    This deliberately does not remove query parameters because source-specific
    IDs may live there. It lowercases scheme and host, strips fragments, and
    removes trailing slashes from paths.
    """

    value = _clean_optional_text(url)
    if value is None:
        return None

    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value.rstrip("/") or None

    path = parts.path.rstrip("/")
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            parts.query,
            "",
        )
    )


@dataclass
class PaperMetadata:
    """Metadata needed to identify and describe a candidate paper."""

    title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    source: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    si_url: Optional[str] = None
    local_si_path: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = str(self.title).strip()
        if not self.title:
            raise ValueError("paper title must not be empty")

        self.authors = _string_list(self.authors)
        self.venue = _clean_optional_text(self.venue)
        self.source = _clean_optional_text(self.source)
        self.doi = normalize_doi(self.doi)
        self.arxiv_id = normalize_arxiv_id(self.arxiv_id)
        self.semantic_scholar_id = normalize_semantic_scholar_id(
            self.semantic_scholar_id
        )
        self.url = canonicalize_url(self.url)
        self.pdf_url = canonicalize_url(self.pdf_url)
        self.si_url = canonicalize_url(self.si_url)
        self.local_si_path = _clean_optional_text(self.local_si_path)
        self.extra = dict(self.extra or {})
        if self.year is not None:
            self.year = int(self.year)

    def identifier_keys(self) -> Set[str]:
        """Return stable local keys used for duplicate detection."""

        keys = set()
        if self.doi:
            keys.add(f"doi:{self.doi}")
        if self.arxiv_id:
            keys.add(f"arxiv:{self.arxiv_id}")
        if self.semantic_scholar_id:
            keys.add(f"semantic_scholar:{self.semantic_scholar_id}")
        if self.url:
            keys.add(f"url:{self.url}")
        if self.pdf_url:
            keys.add(f"pdf_url:{self.pdf_url}")
        return keys

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PaperMetadata":
        known_keys = {
            "title",
            "authors",
            "year",
            "venue",
            "source",
            "doi",
            "arxiv_id",
            "semantic_scholar_id",
            "url",
            "pdf_url",
            "si_url",
            "local_si_path",
            "extra",
        }
        extra = dict(data.get("extra") or {})
        for key, value in data.items():
            if key not in known_keys:
                extra[key] = value

        return cls(
            title=str(data["title"]),
            authors=_string_list(data.get("authors")),
            year=data.get("year"),
            venue=data.get("venue"),
            source=data.get("source"),
            doi=data.get("doi"),
            arxiv_id=data.get("arxiv_id"),
            semantic_scholar_id=data.get("semantic_scholar_id"),
            url=data.get("url"),
            pdf_url=data.get("pdf_url"),
            si_url=data.get("si_url"),
            local_si_path=data.get("local_si_path"),
            extra=extra,
        )


@dataclass
class ScoreBreakdown:
    """Auditable score components for one recommendation."""

    total: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    missing_signals: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.total = float(self.total)
        self.components = {
            str(key): float(value) for key, value in dict(self.components).items()
        }
        self.missing_signals = _string_list(self.missing_signals)
        self.notes = _string_list(self.notes)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScoreBreakdown":
        return cls(
            total=float(data.get("total", 0.0)),
            components=dict(data.get("components") or {}),
            missing_signals=_string_list(data.get("missing_signals")),
            notes=_string_list(data.get("notes")),
        )


@dataclass
class RecommendationRecord:
    """One saved paper recommendation."""

    paper: PaperMetadata
    recommended_at: str = field(default_factory=utc_now_iso)
    user_requirements: str = NO_EXTRA_CONSTRAINTS
    score: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    report_path: Optional[str] = None
    record_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.paper, Mapping):
            self.paper = PaperMetadata.from_dict(self.paper)
        if isinstance(self.score, Mapping):
            self.score = ScoreBreakdown.from_dict(self.score)
        self.recommended_at = str(self.recommended_at).strip() or utc_now_iso()
        self.user_requirements = (
            str(self.user_requirements).strip() or NO_EXTRA_CONSTRAINTS
        )
        self.report_path = _clean_optional_text(self.report_path)
        self.record_id = _clean_optional_text(self.record_id)
        self.extra = dict(self.extra or {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper": self.paper.to_dict(),
            "recommended_at": self.recommended_at,
            "user_requirements": self.user_requirements,
            "score": self.score.to_dict(),
            "report_path": self.report_path,
            "record_id": self.record_id,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecommendationRecord":
        return cls(
            paper=PaperMetadata.from_dict(data["paper"]),
            recommended_at=str(data.get("recommended_at") or utc_now_iso()),
            user_requirements=str(
                data.get("user_requirements") or NO_EXTRA_CONSTRAINTS
            ),
            score=ScoreBreakdown.from_dict(data.get("score") or {}),
            report_path=data.get("report_path"),
            record_id=data.get("record_id"),
            extra=dict(data.get("extra") or {}),
        )


@dataclass
class FeedbackRecord:
    """User feedback for a recommended paper and its explanation."""

    paper_usefulness: int
    explanation_quality: int
    feedback_at: str = field(default_factory=utc_now_iso)
    recommendation_id: Optional[str] = None
    paper_identifiers: List[str] = field(default_factory=list)
    paper_title: Optional[str] = None
    too_basic: bool = False
    too_advanced: bool = False
    wanted_more_math: bool = False
    wanted_more_experiments: bool = False
    wanted_more_code_reproducibility: bool = False
    note: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.paper_usefulness = _validate_score(
            self.paper_usefulness, "paper_usefulness"
        )
        self.explanation_quality = _validate_score(
            self.explanation_quality, "explanation_quality"
        )
        self.feedback_at = str(self.feedback_at).strip() or utc_now_iso()
        self.recommendation_id = _clean_optional_text(self.recommendation_id)
        self.paper_identifiers = _string_list(self.paper_identifiers)
        self.paper_title = _clean_optional_text(self.paper_title)
        self.too_basic = _parse_bool(self.too_basic, "too_basic")
        self.too_advanced = _parse_bool(self.too_advanced, "too_advanced")
        self.wanted_more_math = _parse_bool(
            self.wanted_more_math, "wanted_more_math"
        )
        self.wanted_more_experiments = _parse_bool(
            self.wanted_more_experiments, "wanted_more_experiments"
        )
        self.wanted_more_code_reproducibility = _parse_bool(
            self.wanted_more_code_reproducibility,
            "wanted_more_code_reproducibility",
        )
        self.note = str(self.note).strip()
        self.extra = dict(self.extra or {})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FeedbackRecord":
        return cls(
            paper_usefulness=int(data["paper_usefulness"]),
            explanation_quality=int(data["explanation_quality"]),
            feedback_at=str(data.get("feedback_at") or utc_now_iso()),
            recommendation_id=data.get("recommendation_id"),
            paper_identifiers=_string_list(data.get("paper_identifiers")),
            paper_title=data.get("paper_title"),
            too_basic=data.get("too_basic", False),
            too_advanced=data.get("too_advanced", False),
            wanted_more_math=data.get("wanted_more_math", False),
            wanted_more_experiments=data.get("wanted_more_experiments", False),
            wanted_more_code_reproducibility=data.get(
                "wanted_more_code_reproducibility", False
            ),
            note=str(data.get("note") or ""),
            extra=dict(data.get("extra") or {}),
        )


@dataclass
class ReaderProfile:
    """Optional local preference profile for future runs."""

    preferred_fields: List[str] = field(default_factory=list)
    free_text_preference: str = ""
    explanation_style: str = DEFAULT_EXPLANATION_STYLE
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.preferred_fields = _string_list(self.preferred_fields)
        self.free_text_preference = str(self.free_text_preference or "").strip()
        self.explanation_style = (
            str(self.explanation_style or "").strip() or DEFAULT_EXPLANATION_STYLE
        )
        self.extra = dict(self.extra or {})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReaderProfile":
        return cls(
            preferred_fields=_string_list(data.get("preferred_fields")),
            free_text_preference=str(data.get("free_text_preference") or ""),
            explanation_style=str(
                data.get("explanation_style") or DEFAULT_EXPLANATION_STYLE
            ),
            extra=dict(data.get("extra") or {}),
        )


def _validate_score(value: int, field_name: str) -> int:
    score = int(value)
    if score < 1 or score > 5:
        raise ValueError(f"{field_name} must be between 1 and 5")
    return score


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


def shared_identifier_keys(left: PaperMetadata, right: PaperMetadata) -> Set[str]:
    """Return identifier keys shared by two papers."""

    return left.identifier_keys() & right.identifier_keys()


def is_same_paper(left: PaperMetadata, right: PaperMetadata) -> bool:
    """Return whether two metadata records identify the same paper."""

    return bool(shared_identifier_keys(left, right))
