"""Small JSON and JSONL stores for local PaperScout history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, List, Mapping, Optional, TypeVar

from paperscout.storage.schemas import (
    FeedbackRecord,
    PaperMetadata,
    ReaderProfile,
    RecommendationRecord,
    is_same_paper,
)

T = TypeVar("T")


def append_jsonl(path: Path, record: Any) -> None:
    """Append one JSON-serializable record to a JSONL file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_to_jsonable(record), ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Mapping[str, Any]]:
    """Read a JSONL file. Missing files are treated as empty history."""

    path = Path(path)
    if not path.exists():
        return []
    return list(iter_jsonl(path))


def iter_jsonl(path: Path) -> Iterator[Mapping[str, Any]]:
    """Yield parsed JSON objects from a JSONL file."""

    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL record in {path} at line {line_number}"
                ) from exc
            if not isinstance(value, Mapping):
                raise ValueError(
                    f"JSONL record in {path} at line {line_number} is not an object"
                )
            yield value


def load_jsonl(path: Path, factory: Callable[[Mapping[str, Any]], T]) -> List[T]:
    return [factory(record) for record in read_jsonl(path)]


def write_json(path: Path, record: Any) -> None:
    """Write one JSON object atomically enough for local CLI usage."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(_to_jsonable(record), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def read_json(path: Path) -> Optional[Mapping[str, Any]]:
    path = Path(path)
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON file {path} does not contain an object")
    return value


def append_recommendation(path: Path, record: RecommendationRecord) -> None:
    append_jsonl(path, record)


def load_recommendations(path: Path) -> List[RecommendationRecord]:
    return load_jsonl(path, RecommendationRecord.from_dict)


def append_feedback(path: Path, record: FeedbackRecord) -> None:
    append_jsonl(path, record)


def load_feedback(path: Path) -> List[FeedbackRecord]:
    return load_jsonl(path, FeedbackRecord.from_dict)


def save_profile(path: Path, profile: ReaderProfile) -> None:
    write_json(path, profile)


def load_profile(path: Path) -> Optional[ReaderProfile]:
    data = read_json(path)
    if data is None:
        return None
    return ReaderProfile.from_dict(data)


def find_duplicate_recommendation(
    paper: PaperMetadata, recommendations: Iterable[RecommendationRecord]
) -> Optional[RecommendationRecord]:
    """Return the first prior recommendation that identifies the same paper."""

    for recommendation in recommendations:
        if is_same_paper(paper, recommendation.paper):
            return recommendation
    return None


def has_recommended_paper(
    paper: PaperMetadata, recommendations: Iterable[RecommendationRecord]
) -> bool:
    return find_duplicate_recommendation(paper, recommendations) is not None


def _to_jsonable(record: Any) -> Any:
    if hasattr(record, "to_dict"):
        return record.to_dict()
    return record
