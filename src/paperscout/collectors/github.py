"""GitHub repository metadata collector."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from paperscout.collectors.cache import CachedHttpClient

GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


@dataclass
class GitHubRepository:
    """Repository metadata useful as paper attention evidence."""

    full_name: str
    html_url: str
    description: Optional[str] = None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    language: Optional[str] = None
    pushed_at: Optional[str] = None
    updated_at: Optional[str] = None
    topics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_attention(self) -> Dict[str, Any]:
        return {
            "github_stars": self.stars,
            "github_forks": self.forks,
            "github_open_issues": self.open_issues,
            "github_pushed_at": self.pushed_at,
            "source_confidence": 0.6,
        }


def search_github_repositories(
    query: str,
    *,
    max_results: int = 10,
    token: Optional[str] = None,
    require_token: bool = False,
    client: Optional[CachedHttpClient] = None,
    refresh: bool = False,
) -> List[GitHubRepository]:
    """Search GitHub repositories by stars for rough code-attention evidence."""

    client = client or CachedHttpClient()
    data = client.get_json(
        f"{GITHUB_API_URL}/search/repositories",
        params={
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(max_results, 100),
        },
        headers=github_headers(
            token=resolve_github_token(token=token, require_token=require_token)
        ),
        cache_key_prefix="github_search_repositories",
        refresh=refresh,
    )
    items = data.get("items") or []
    if not isinstance(items, list):
        raise ValueError("GitHub search response field 'items' is not a list")
    return [
        github_repository_from_api(item)
        for item in items
        if isinstance(item, Mapping)
    ]


def fetch_github_repository(
    full_name: str,
    *,
    token: Optional[str] = None,
    require_token: bool = False,
    client: Optional[CachedHttpClient] = None,
    refresh: bool = False,
) -> GitHubRepository:
    client = client or CachedHttpClient()
    data = client.get_json(
        f"{GITHUB_API_URL}/repos/{full_name}",
        headers=github_headers(
            token=resolve_github_token(token=token, require_token=require_token)
        ),
        cache_key_prefix="github_repository",
        refresh=refresh,
    )
    return github_repository_from_api(data)


def resolve_github_token(
    *,
    token: Optional[str] = None,
    require_token: bool = False,
) -> Optional[str]:
    resolved_token = token or os.getenv("GITHUB_TOKEN")
    if require_token and not resolved_token:
        raise RuntimeError("GITHUB_TOKEN is required for this GitHub API call.")
    return resolved_token


def github_headers(token: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_repository_from_api(data: Mapping[str, Any]) -> GitHubRepository:
    return GitHubRepository(
        full_name=str(data["full_name"]),
        html_url=str(data["html_url"]),
        description=data.get("description"),
        stars=int(data.get("stargazers_count") or 0),
        forks=int(data.get("forks_count") or 0),
        open_issues=int(data.get("open_issues_count") or 0),
        language=data.get("language"),
        pushed_at=data.get("pushed_at"),
        updated_at=data.get("updated_at"),
        topics=[
            str(topic)
            for topic in data.get("topics") or []
            if str(topic).strip()
        ],
    )
