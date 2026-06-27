"""Manual candidate loading for early PaperScout workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from paperscout.storage.schemas import PaperMetadata


@dataclass
class ManualCandidate:
    """A paper candidate with manually supplied attention signals."""

    paper: PaperMetadata
    attention: Dict[str, Any] = field(default_factory=dict)
    requirement_match_score: float = 0.0
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.paper, Mapping):
            self.paper = PaperMetadata.from_dict(self.paper)
        self.attention = dict(self.attention or {})
        self.requirement_match_score = float(self.requirement_match_score)
        self.notes = [str(note).strip() for note in self.notes if str(note).strip()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper": self.paper.to_dict(),
            "attention": self.attention,
            "requirement_match_score": self.requirement_match_score,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ManualCandidate":
        if "paper" not in data:
            raise ValueError("manual candidate is missing required 'paper' object")
        return cls(
            paper=PaperMetadata.from_dict(_expect_mapping(data["paper"], "paper")),
            attention=dict(data.get("attention") or {}),
            requirement_match_score=float(data.get("requirement_match_score", 0.0)),
            notes=_string_list(data.get("notes")),
        )


def load_manual_candidates(path: Path) -> List[ManualCandidate]:
    """Load manual paper candidates from a JSON file.

    The file may either contain a top-level list of candidates or an object with
    a `candidates` list. YAML is intentionally not supported yet to keep the
    first manual mode dependency-free.
    """

    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("manual candidate files currently must be JSON")

    raw_data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw_data, Mapping):
        raw_candidates = raw_data.get("candidates")
    else:
        raw_candidates = raw_data

    if not isinstance(raw_candidates, list):
        raise ValueError("manual candidate file must contain a candidate list")

    return [
        ManualCandidate.from_dict(_expect_mapping(candidate, "candidate"))
        for candidate in raw_candidates
    ]


def dump_manual_candidates(path: Path, candidates: Iterable[ManualCandidate]) -> None:
    """Write manual candidates to JSON for examples or small curated runs."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"candidates": [candidate.to_dict() for candidate in candidates]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _expect_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _string_list(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(value).strip() for value in values if str(value).strip()]
