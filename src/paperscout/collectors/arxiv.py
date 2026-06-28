"""arXiv metadata collector."""

from __future__ import annotations

import re
from typing import List, Optional
from xml.etree import ElementTree

from paperscout.collectors.cache import CachedHttpClient
from paperscout.collectors.manual import ManualCandidate
from paperscout.storage.schemas import PaperMetadata

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
GITHUB_REPOSITORY_URL_PATTERN = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
)


def search_arxiv(
    query: str,
    *,
    max_results: int = 10,
    start: int = 0,
    sort_by: str = "lastUpdatedDate",
    sort_order: str = "descending",
    client: Optional[CachedHttpClient] = None,
    refresh: bool = False,
) -> List[ManualCandidate]:
    """Search arXiv and return normalized manual candidates."""

    client = client or CachedHttpClient(min_interval_seconds=3.0)
    text = client.get_text(
        ARXIV_API_URL,
        params={
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        },
        cache_key_prefix="arxiv",
        refresh=refresh,
    )
    return parse_arxiv_feed(text)


def parse_arxiv_feed(feed_text: str) -> List[ManualCandidate]:
    root = ElementTree.fromstring(feed_text)
    candidates = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        title = _entry_text(entry, "title")
        if not title:
            continue
        authors = [
            _child_text(author, "name")
            for author in entry.findall(f"{ATOM_NS}author")
            if _child_text(author, "name")
        ]
        entry_id = _entry_text(entry, "id")
        arxiv_id = _extract_arxiv_id(entry_id)
        pdf_url = _extract_pdf_url(entry)
        published = _entry_text(entry, "published")
        year = int(published[:4]) if published and published[:4].isdigit() else None
        categories = [
            category.attrib["term"]
            for category in entry.findall(f"{ATOM_NS}category")
            if category.attrib.get("term")
        ]
        summary = _entry_text(entry, "summary")
        extra = {
            "summary": summary,
            "published": published,
            "updated": _entry_text(entry, "updated"),
            "categories": categories,
        }
        github_urls = extract_github_urls(summary)
        if github_urls:
            extra["github_urls"] = github_urls
            if len(github_urls) == 1:
                extra["github_url"] = github_urls[0]

        paper = PaperMetadata(
            title=" ".join(title.split()),
            authors=authors,
            year=year,
            source="arxiv",
            doi=_entry_text(entry, "doi", namespace=ARXIV_NS),
            arxiv_id=arxiv_id,
            url=entry_id,
            pdf_url=pdf_url,
            extra=extra,
        )
        candidates.append(
            ManualCandidate(
                paper=paper,
                attention={"source_confidence": 0.7},
                notes=[
                    "arXiv metadata only; attention metrics require another source."
                ],
            )
        )
    return candidates


def _entry_text(
    entry: ElementTree.Element,
    tag: str,
    *,
    namespace: str = ATOM_NS,
) -> Optional[str]:
    child = entry.find(f"{namespace}{tag}")
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _child_text(entry: ElementTree.Element, tag: str) -> Optional[str]:
    child = entry.find(f"{ATOM_NS}{tag}")
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _extract_arxiv_id(entry_id: Optional[str]) -> Optional[str]:
    if entry_id is None:
        return None
    return entry_id.rstrip("/").split("/")[-1]


def _extract_pdf_url(entry: ElementTree.Element) -> Optional[str]:
    for link in entry.findall(f"{ATOM_NS}link"):
        if (
            link.attrib.get("title") == "pdf"
            or link.attrib.get("type") == "application/pdf"
        ):
            return link.attrib.get("href")
    return None


def extract_github_urls(text: Optional[str]) -> List[str]:
    if not text:
        return []

    urls = []
    seen = set()
    for match in GITHUB_REPOSITORY_URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(".,);]")
        if url.endswith(".git"):
            url = url[:-4]
        if url not in seen:
            urls.append(url)
            seen.add(url)
    return urls
