"""Candidate paper metadata collectors."""

from paperscout.collectors.arxiv import parse_arxiv_feed, search_arxiv
from paperscout.collectors.cache import CachedHttpClient, HttpRequestError, HttpResponse
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

__all__ = [
    "CachedHttpClient",
    "GitHubRepository",
    "HttpRequestError",
    "HttpResponse",
    "ManualCandidate",
    "attach_github_repositories",
    "collect_explicit_github_full_names",
    "dump_manual_candidates",
    "fetch_github_repository",
    "load_manual_candidates",
    "merge_candidate_lists",
    "parse_arxiv_feed",
    "search_arxiv",
    "search_github_repositories",
    "search_semantic_scholar",
]
