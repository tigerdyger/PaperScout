"""Merge candidate metadata from multiple collectors."""

from __future__ import annotations

from typing import Iterable, List, Optional
from urllib.parse import urlsplit

from paperscout.collectors.github import GitHubRepository
from paperscout.collectors.manual import ManualCandidate
from paperscout.storage.schemas import PaperMetadata, is_same_paper

REPOSITORY_HINT_KEYS = {
    "github_url",
    "github_urls",
    "code_url",
    "code_urls",
    "repository_url",
    "repository_urls",
    "github_full_name",
}


def merge_candidate_lists(*candidate_lists: Iterable[ManualCandidate]) -> List[ManualCandidate]:
    """Merge candidate lists using stable paper identifiers only."""

    merged: List[ManualCandidate] = []
    for candidates in candidate_lists:
        for candidate in candidates:
            existing = _find_same_candidate(candidate, merged)
            if existing is None:
                merged.append(candidate)
            else:
                _merge_candidate_into(existing, candidate)
    return merged


def attach_github_repositories(
    candidates: Iterable[ManualCandidate],
    repositories: Iterable[GitHubRepository],
) -> int:
    """Attach GitHub repository attention when metadata explicitly identifies a repo.

    This intentionally avoids fuzzy title matching. A wrong paper-code match is
    worse than a missing code signal at this stage.
    """

    attached = 0
    repository_list = list(repositories)
    for candidate in candidates:
        repository = _find_explicit_repository_match(candidate, repository_list)
        if repository is None:
            continue
        candidate.attention = _merge_attention(
            candidate.attention,
            repository.to_attention(),
        )
        candidate.paper.extra["github_repository"] = repository.to_dict()
        note = f"GitHub repository matched explicitly: {repository.full_name}"
        if note not in candidate.notes:
            candidate.notes.append(note)
        attached += 1
    return attached


def collect_explicit_github_full_names(
    candidates: Iterable[ManualCandidate],
) -> List[str]:
    full_names = []
    seen = set()
    for candidate in candidates:
        for hint in _repository_hints(candidate):
            full_name = _repository_full_name_from_hint(hint)
            if full_name and full_name not in seen:
                full_names.append(full_name)
                seen.add(full_name)
    return full_names


def _find_same_candidate(
    candidate: ManualCandidate,
    candidates: Iterable[ManualCandidate],
) -> Optional[ManualCandidate]:
    for existing in candidates:
        if is_same_paper(candidate.paper, existing.paper):
            return existing
    return None


def _merge_candidate_into(target: ManualCandidate, incoming: ManualCandidate) -> None:
    target.paper = _merge_paper_metadata(target.paper, incoming.paper)
    target.attention = _merge_attention(target.attention, incoming.attention)
    target.requirement_match_score = max(
        target.requirement_match_score,
        incoming.requirement_match_score,
    )
    for note in incoming.notes:
        if note not in target.notes:
            target.notes.append(note)


def _merge_paper_metadata(left: PaperMetadata, right: PaperMetadata) -> PaperMetadata:
    merged = left.to_dict()
    for key, value in right.to_dict().items():
        if key == "extra":
            merged["extra"] = _merge_extra(left.extra, right.extra)
            continue
        if _is_missing(merged.get(key)) and not _is_missing(value):
            merged[key] = value
    merged["extra"] = _merge_source_provenance(
        merged.get("extra") or {},
        left.source,
        right.source,
    )
    return PaperMetadata.from_dict(merged)


def _merge_extra(left: dict, right: dict) -> dict:
    merged = dict(left or {})
    for key, value in dict(right or {}).items():
        if key not in merged or _is_missing(merged[key]):
            merged[key] = value
        elif key == "sources":
            merged[key] = _ordered_unique(_as_list(merged[key]) + _as_list(value))
    return merged


def _merge_source_provenance(extra: dict, *sources: Optional[str]) -> dict:
    merged = dict(extra or {})
    source_values = _as_list(merged.get("sources")) if merged.get("sources") else []
    source_values.extend(source for source in sources if source)
    if source_values:
        merged["sources"] = _ordered_unique(source_values)
    return merged


def _merge_attention(left: dict, right: dict) -> dict:
    merged = dict(left or {})
    for key, value in dict(right or {}).items():
        if value is None:
            continue
        if key not in merged or merged[key] is None:
            merged[key] = value
            continue
        if isinstance(merged[key], (int, float)) and isinstance(value, (int, float)):
            merged[key] = max(merged[key], value)
    return merged


def _find_explicit_repository_match(
    candidate: ManualCandidate,
    repositories: Iterable[GitHubRepository],
) -> Optional[GitHubRepository]:
    repository_hints = set(_repository_hints(candidate))
    if not repository_hints:
        return None

    for repository in repositories:
        if _normalize_repository_hint(repository.full_name) in repository_hints:
            return repository
        if _normalize_repository_hint(repository.html_url) in repository_hints:
            return repository
    return None


def _repository_hints(candidate: ManualCandidate) -> List[str]:
    hints = []
    seen = set()
    for key, value in candidate.paper.extra.items():
        if key not in REPOSITORY_HINT_KEYS:
            continue
        for item in _as_list(value):
            normalized = _normalize_repository_hint(item)
            if normalized and normalized not in seen:
                hints.append(normalized)
                seen.add(normalized)
    return hints


def _normalize_repository_hint(value: object) -> str:
    hint = str(value).strip().lower().rstrip("/")
    if hint.endswith(".git"):
        hint = hint[:-4]
    return hint


def _repository_full_name_from_hint(hint: str) -> Optional[str]:
    if "://" not in hint:
        return hint if _looks_like_github_full_name(hint) else None

    parsed = urlsplit(hint)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    full_name = f"{parts[0]}/{parts[1]}"
    return full_name if _looks_like_github_full_name(full_name) else None


def _looks_like_github_full_name(value: str) -> bool:
    parts = value.split("/")
    if len(parts) != 2:
        return False
    return all(parts) and not any(part in {".", ".."} for part in parts)


def _is_missing(value: object) -> bool:
    return value is None or value == "" or value == []


def _as_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _ordered_unique(values: Iterable[object]) -> List[str]:
    unique_values = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            unique_values.append(text)
            seen.add(text)
    return unique_values
