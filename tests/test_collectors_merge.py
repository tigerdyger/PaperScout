from paperscout.collectors.github import GitHubRepository
from paperscout.collectors.manual import ManualCandidate
from paperscout.collectors.merge import (
    attach_github_repositories,
    collect_explicit_github_full_names,
    merge_candidate_lists,
)
from paperscout.storage.schemas import PaperMetadata


def test_merge_candidate_lists_merges_by_stable_identifier() -> None:
    arxiv_candidate = ManualCandidate(
        paper=PaperMetadata(
            title="arXiv title",
            arxiv_id="2401.00001",
            source="arxiv",
            url="https://arxiv.org/abs/2401.00001",
            extra={"summary": "from arxiv"},
        ),
        attention={"source_confidence": 0.7},
        notes=["from arxiv"],
    )
    semantic_scholar_candidate = ManualCandidate(
        paper=PaperMetadata(
            title="Semantic Scholar title",
            arxiv_id="https://arxiv.org/abs/2401.00001",
            doi="10.1000/example",
            semantic_scholar_id="abc123",
            source="semantic_scholar",
            extra={"citation_count": 10},
        ),
        attention={
            "source_confidence": 0.8,
            "semantic_scholar_citation_count": 10,
        },
        notes=["from semantic scholar"],
    )

    merged = merge_candidate_lists([arxiv_candidate], [semantic_scholar_candidate])

    assert len(merged) == 1
    assert merged[0].paper.title == "arXiv title"
    assert merged[0].paper.doi == "10.1000/example"
    assert merged[0].paper.semantic_scholar_id == "abc123"
    assert merged[0].paper.extra["sources"] == ["arxiv", "semantic_scholar"]
    assert merged[0].attention["source_confidence"] == 0.8
    assert merged[0].attention["semantic_scholar_citation_count"] == 10
    assert merged[0].notes == ["from arxiv", "from semantic scholar"]


def test_merge_candidate_lists_keeps_unmatched_candidates_separate() -> None:
    first = ManualCandidate(paper=PaperMetadata(title="A", arxiv_id="2401.00001"))
    second = ManualCandidate(paper=PaperMetadata(title="B", arxiv_id="2401.00002"))

    merged = merge_candidate_lists([first], [second])

    assert [candidate.paper.title for candidate in merged] == ["A", "B"]


def test_attach_github_repositories_requires_explicit_metadata_match() -> None:
    matched = ManualCandidate(
        paper=PaperMetadata(
            title="With code",
            arxiv_id="2401.00001",
            extra={"github_url": "https://github.com/owner/repo"},
        )
    )
    unmatched = ManualCandidate(
        paper=PaperMetadata(
            title="No explicit code",
            arxiv_id="2401.00002",
        )
    )
    repositories = [
        GitHubRepository(
            full_name="owner/repo",
            html_url="https://github.com/owner/repo",
            stars=50,
            forks=3,
        )
    ]

    attached = attach_github_repositories([matched, unmatched], repositories)

    assert attached == 1
    assert matched.attention["github_stars"] == 50
    assert matched.paper.extra["github_repository"]["full_name"] == "owner/repo"
    assert "github_stars" not in unmatched.attention


def test_attach_github_repositories_accepts_url_lists() -> None:
    candidate = ManualCandidate(
        paper=PaperMetadata(
            title="With code list",
            arxiv_id="2401.00003",
            extra={"github_urls": ["https://github.com/owner/repo.git"]},
        )
    )
    repositories = [
        GitHubRepository(
            full_name="owner/repo",
            html_url="https://github.com/owner/repo",
            stars=8,
        )
    ]

    attached = attach_github_repositories([candidate], repositories)

    assert attached == 1
    assert candidate.attention["github_stars"] == 8


def test_collect_explicit_github_full_names_from_candidate_metadata() -> None:
    candidates = [
        ManualCandidate(
            paper=PaperMetadata(
                title="With code",
                arxiv_id="2401.00004",
                extra={
                    "github_url": "https://github.com/Owner/Repo/",
                    "code_urls": [
                        "https://example.org/not-github",
                        "https://github.com/other/project",
                    ],
                },
            )
        ),
        ManualCandidate(
            paper=PaperMetadata(
                title="With full name",
                arxiv_id="2401.00005",
                extra={"github_full_name": "owner/repo"},
            )
        ),
    ]

    assert collect_explicit_github_full_names(candidates) == [
        "owner/repo",
        "other/project",
    ]
