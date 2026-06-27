import pytest

from paperscout.storage.schemas import (
    FeedbackRecord,
    PaperMetadata,
    RecommendationRecord,
    ScoreBreakdown,
    canonicalize_url,
    is_same_paper,
    normalize_arxiv_id,
    normalize_doi,
    shared_identifier_keys,
)


def test_identifier_normalization_and_duplicate_keys() -> None:
    paper = PaperMetadata(
        title="Attention Is All You Need",
        doi="https://doi.org/10.48550/arXiv.1706.03762",
        arxiv_id="https://arxiv.org/pdf/1706.03762.pdf",
        semantic_scholar_id="ABC123",
        url="https://ARXIV.org/abs/1706.03762/",
        pdf_url="https://arxiv.org/pdf/1706.03762.pdf#page=1",
    )

    assert paper.doi == "10.48550/arxiv.1706.03762"
    assert paper.arxiv_id == "1706.03762"
    assert paper.semantic_scholar_id == "abc123"
    assert paper.url == "https://arxiv.org/abs/1706.03762"
    assert paper.pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"
    assert paper.identifier_keys() == {
        "doi:10.48550/arxiv.1706.03762",
        "arxiv:1706.03762",
        "semantic_scholar:abc123",
        "url:https://arxiv.org/abs/1706.03762",
        "pdf_url:https://arxiv.org/pdf/1706.03762.pdf",
    }


def test_is_same_paper_uses_shared_identifiers() -> None:
    first = PaperMetadata(title="First title", arxiv_id="arXiv:2401.00001")
    second = PaperMetadata(
        title="Changed title",
        arxiv_id="https://arxiv.org/abs/2401.00001",
    )
    unrelated = PaperMetadata(title="Other", doi="10.1000/example")

    assert is_same_paper(first, second)
    assert shared_identifier_keys(first, second) == {"arxiv:2401.00001"}
    assert not is_same_paper(first, unrelated)


def test_record_round_trip_preserves_nested_schema() -> None:
    record = RecommendationRecord(
        paper=PaperMetadata(
            title="A useful paper",
            authors=["Alice", " Bob "],
            year="2025",
            doi="DOI:10.1000/Example",
        ),
        user_requirements="AI4S with careful experiments",
        score=ScoreBreakdown(
            total=3,
            components={"recent_attention": 2, "source_confidence": 1},
            missing_signals=["video_count"],
        ),
        report_path="reports/a-useful-paper.md",
    )

    restored = RecommendationRecord.from_dict(record.to_dict())

    assert restored.paper.authors == ["Alice", "Bob"]
    assert restored.paper.year == 2025
    assert restored.paper.doi == "10.1000/example"
    assert restored.score.total == 3.0
    assert restored.score.components["recent_attention"] == 2.0
    assert restored.report_path == "reports/a-useful-paper.md"


def test_feedback_scores_must_be_between_one_and_five() -> None:
    FeedbackRecord(paper_usefulness=1, explanation_quality=5)

    with pytest.raises(ValueError, match="paper_usefulness"):
        FeedbackRecord(paper_usefulness=0, explanation_quality=5)

    with pytest.raises(ValueError, match="explanation_quality"):
        FeedbackRecord(paper_usefulness=3, explanation_quality=6)


def test_feedback_boolean_fields_are_parsed_strictly() -> None:
    feedback = FeedbackRecord.from_dict(
        {
            "paper_usefulness": 4,
            "explanation_quality": 5,
            "too_basic": "false",
            "too_advanced": "0",
            "wanted_more_math": "true",
            "wanted_more_experiments": "yes",
            "wanted_more_code_reproducibility": 1,
        }
    )

    assert feedback.too_basic is False
    assert feedback.too_advanced is False
    assert feedback.wanted_more_math is True
    assert feedback.wanted_more_experiments is True
    assert feedback.wanted_more_code_reproducibility is True

    with pytest.raises(ValueError, match="too_basic"):
        FeedbackRecord(
            paper_usefulness=4,
            explanation_quality=5,
            too_basic="maybe",
        )


def test_empty_title_is_rejected() -> None:
    with pytest.raises(ValueError, match="title"):
        PaperMetadata(title="  ")


def test_standalone_normalizers() -> None:
    assert normalize_doi("DOI:10.1234/ABC") == "10.1234/abc"
    assert normalize_arxiv_id("arXiv:2301.12345v2") == "2301.12345v2"
    assert (
        canonicalize_url("HTTPS://Example.COM/some/path/#fragment")
        == "https://example.com/some/path"
    )
