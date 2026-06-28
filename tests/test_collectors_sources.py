import json

import pytest

from paperscout.collectors.arxiv import (
    extract_github_urls,
    parse_arxiv_feed,
    search_arxiv,
)
from paperscout.collectors.cache import CachedHttpClient, HttpResponse
from paperscout.collectors.github import (
    fetch_github_repository,
    github_headers,
    resolve_github_token,
    search_github_repositories,
)
from paperscout.collectors.semantic_scholar import (
    resolve_semantic_scholar_api_key,
    search_semantic_scholar,
    semantic_scholar_paper_to_candidate,
)


ARXIV_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/2401.00001v1</id>
    <updated>2024-01-02T00:00:00Z</updated>
    <published>2024-01-01T00:00:00Z</published>
    <title> Example AI for Chemistry </title>
    <summary>Example summary. Code: https://github.com/owner/repo.</summary>
    <author><name>Alice Example</name></author>
    <author><name>Bob Example</name></author>
    <arxiv:doi>10.48550/arXiv.2401.00001</arxiv:doi>
    <category term="cs.LG" />
    <category term="physics.chem-ph" />
    <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" />
    <link title="pdf" href="https://arxiv.org/pdf/2401.00001v1" />
  </entry>
</feed>
"""


def test_parse_arxiv_feed_normalizes_candidates() -> None:
    candidates = parse_arxiv_feed(ARXIV_FEED)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.paper.title == "Example AI for Chemistry"
    assert candidate.paper.authors == ["Alice Example", "Bob Example"]
    assert candidate.paper.year == 2024
    assert candidate.paper.arxiv_id == "2401.00001v1"
    assert candidate.paper.doi == "10.48550/arxiv.2401.00001"
    assert candidate.paper.pdf_url == "https://arxiv.org/pdf/2401.00001v1"
    assert candidate.paper.extra["categories"] == ["cs.LG", "physics.chem-ph"]
    assert candidate.paper.extra["github_url"] == "https://github.com/owner/repo"
    assert candidate.paper.extra["github_urls"] == ["https://github.com/owner/repo"]
    assert candidate.attention == {"source_confidence": 0.7}


def test_extract_github_urls_keeps_explicit_repository_links_only() -> None:
    urls = extract_github_urls(
        "Code: https://github.com/owner/repo. "
        "Docs: https://github.com/owner/repo/blob/main/README.md "
        "Clone: https://github.com/other/project.git"
    )

    assert urls == [
        "https://github.com/owner/repo",
        "https://github.com/other/project",
    ]


def test_search_arxiv_uses_expected_query_params(tmp_path) -> None:
    seen_urls = []

    def fake_transport(url, headers, timeout):
        seen_urls.append(url)
        return HttpResponse(status=200, body=ARXIV_FEED)

    client = CachedHttpClient(cache_dir=tmp_path / "cache", transport=fake_transport)

    candidates = search_arxiv(
        "cat:cs.LG",
        max_results=3,
        client=client,
    )

    assert len(candidates) == 1
    assert "search_query=cat%3Acs.LG" in seen_urls[0]
    assert "max_results=3" in seen_urls[0]
    assert "sortBy=lastUpdatedDate" in seen_urls[0]


def test_semantic_scholar_candidate_conversion() -> None:
    candidate = semantic_scholar_paper_to_candidate(
        {
            "paperId": "abc123",
            "title": "Semantic Scholar Paper",
            "year": 2025,
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
            "url": "https://www.semanticscholar.org/paper/abc123",
            "externalIds": {"DOI": "10.1000/SS", "ArXiv": "2501.00001"},
            "citationCount": 42,
            "influentialCitationCount": 7,
            "publicationVenue": {"name": "Example Venue"},
            "openAccessPdf": {"url": "https://example.org/paper.pdf"},
        }
    )

    assert candidate.paper.title == "Semantic Scholar Paper"
    assert candidate.paper.semantic_scholar_id == "abc123"
    assert candidate.paper.doi == "10.1000/ss"
    assert candidate.paper.arxiv_id == "2501.00001"
    assert candidate.paper.venue == "Example Venue"
    assert candidate.attention["semantic_scholar_citation_count"] == 42
    assert "lifetime metadata" in candidate.notes[0]


def test_search_semantic_scholar_uses_api_key_header(tmp_path) -> None:
    seen_headers = []

    def fake_transport(url, headers, timeout):
        seen_headers.append(headers)
        return HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "data": [
                        {
                            "paperId": "abc123",
                            "title": "Paper",
                            "authors": [],
                        }
                    ]
                }
            ),
        )

    client = CachedHttpClient(cache_dir=tmp_path / "cache", transport=fake_transport)
    candidates = search_semantic_scholar(
        "AI chemistry",
        api_key="secret",
        client=client,
    )

    assert len(candidates) == 1
    assert seen_headers[0]["x-api-key"] == "secret"


def test_required_api_keys_have_clear_errors(monkeypatch) -> None:
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="SEMANTIC_SCHOLAR_API_KEY"):
        resolve_semantic_scholar_api_key(require_api_key=True)

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        resolve_github_token(require_token=True)


def test_github_repository_search_and_attention(tmp_path) -> None:
    seen_headers = []

    def fake_transport(url, headers, timeout):
        seen_headers.append(headers)
        return HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "items": [
                        {
                            "full_name": "owner/repo",
                            "html_url": "https://github.com/owner/repo",
                            "description": "Example",
                            "stargazers_count": 123,
                            "forks_count": 4,
                            "open_issues_count": 2,
                            "language": "Python",
                            "pushed_at": "2026-01-01T00:00:00Z",
                            "updated_at": "2026-01-02T00:00:00Z",
                            "topics": ["ai4s", "chemistry"],
                        }
                    ]
                }
            ),
        )

    client = CachedHttpClient(cache_dir=tmp_path / "cache", transport=fake_transport)
    repositories = search_github_repositories(
        "AI chemistry",
        token="secret",
        client=client,
    )

    assert len(repositories) == 1
    repository = repositories[0]
    assert repository.full_name == "owner/repo"
    assert repository.stars == 123
    assert repository.topics == ["ai4s", "chemistry"]
    assert repository.to_attention()["github_stars"] == 123
    assert seen_headers[0]["Authorization"] == "Bearer secret"
    assert github_headers()["X-GitHub-Api-Version"] == "2022-11-28"


def test_fetch_github_repository(tmp_path) -> None:
    def fake_transport(url, headers, timeout):
        assert url.endswith("/repos/owner/repo")
        return HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "full_name": "owner/repo",
                    "html_url": "https://github.com/owner/repo",
                    "stargazers_count": 5,
                }
            ),
        )

    client = CachedHttpClient(cache_dir=tmp_path / "cache", transport=fake_transport)
    repository = fetch_github_repository("owner/repo", client=client)

    assert repository.full_name == "owner/repo"
    assert repository.html_url == "https://github.com/owner/repo"
    assert repository.stars == 5
