"""Semantic Scholar Graph API collector."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional

from paperscout.collectors.cache import CachedHttpClient
from paperscout.collectors.manual import ManualCandidate
from paperscout.storage.schemas import PaperMetadata

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
DEFAULT_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "year",
        "authors",
        "url",
        "externalIds",
        "citationCount",
        "influentialCitationCount",
        "publicationVenue",
        "openAccessPdf",
    ]
)


def search_semantic_scholar(
    query: str,
    *,
    limit: int = 10,
    api_key: Optional[str] = None,
    require_api_key: bool = False,
    client: Optional[CachedHttpClient] = None,
    refresh: bool = False,
) -> List[ManualCandidate]:
    """Search Semantic Scholar and return normalized manual candidates."""

    resolved_key = resolve_semantic_scholar_api_key(
        api_key=api_key,
        require_api_key=require_api_key,
    )
    headers = {}
    if resolved_key:
        headers["x-api-key"] = resolved_key

    client = client or CachedHttpClient()
    data = client.get_json(
        SEMANTIC_SCHOLAR_SEARCH_URL,
        params={
            "query": query,
            "limit": limit,
            "fields": DEFAULT_FIELDS,
        },
        headers=headers,
        cache_key_prefix="semantic_scholar",
        refresh=refresh,
    )
    papers = data.get("data") or []
    if not isinstance(papers, list):
        raise ValueError("Semantic Scholar response field 'data' is not a list")
    return [
        semantic_scholar_paper_to_candidate(paper)
        for paper in papers
        if isinstance(paper, Mapping)
    ]


def resolve_semantic_scholar_api_key(
    *,
    api_key: Optional[str] = None,
    require_api_key: bool = False,
) -> Optional[str]:
    resolved_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if require_api_key and not resolved_key:
        raise RuntimeError(
            "SEMANTIC_SCHOLAR_API_KEY is required for this Semantic Scholar call."
        )
    return resolved_key


def semantic_scholar_paper_to_candidate(paper: Mapping[str, Any]) -> ManualCandidate:
    external_ids = _mapping(paper.get("externalIds"))
    publication_venue = _mapping(paper.get("publicationVenue"))
    open_access_pdf = _mapping(paper.get("openAccessPdf"))
    citation_count = _optional_int(paper.get("citationCount"))
    influential_citation_count = _optional_int(paper.get("influentialCitationCount"))

    metadata = PaperMetadata(
        title=str(paper.get("title") or "").strip(),
        authors=[
            str(author.get("name")).strip()
            for author in paper.get("authors") or []
            if isinstance(author, Mapping) and author.get("name")
        ],
        year=paper.get("year"),
        venue=publication_venue.get("name"),
        source="semantic_scholar",
        doi=external_ids.get("DOI"),
        arxiv_id=external_ids.get("ArXiv"),
        semantic_scholar_id=paper.get("paperId"),
        url=paper.get("url"),
        pdf_url=open_access_pdf.get("url"),
        extra={
            "citation_count": citation_count,
            "influential_citation_count": influential_citation_count,
        },
    )
    return ManualCandidate(
        paper=metadata,
        attention={
            "source_confidence": 0.8,
            "semantic_scholar_citation_count": citation_count,
            "semantic_scholar_influential_citation_count": influential_citation_count,
        },
        notes=[
            "Semantic Scholar citation counts are lifetime metadata, not recent attention."
        ],
    )


def _mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)
