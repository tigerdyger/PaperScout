import pytest

from paperscout.feedback import (
    build_feedback_record,
    feedback_summary_lines,
    profile_from_feedback,
    select_recommendation_for_feedback,
    summarize_feedback,
)
from paperscout.storage.schemas import (
    FeedbackRecord,
    PaperMetadata,
    ReaderProfile,
    RecommendationRecord,
)


def test_build_feedback_record_copies_recommendation_identity() -> None:
    recommendation = RecommendationRecord(
        paper=PaperMetadata(
            title="Useful Paper",
            arxiv_id="2401.00001",
            doi="10.1000/useful",
        ),
        record_id="rec-001",
    )

    feedback = build_feedback_record(
        recommendation,
        paper_usefulness=5,
        explanation_quality=4,
        wanted_more_math=True,
        note="多讲推导",
    )

    assert feedback.recommendation_id == "rec-001"
    assert feedback.paper_title == "Useful Paper"
    assert feedback.paper_identifiers == [
        "arxiv:2401.00001",
        "doi:10.1000/useful",
    ]
    assert feedback.wanted_more_math is True
    assert feedback.note == "多讲推导"


def test_select_recommendation_for_feedback_defaults_to_latest() -> None:
    first = RecommendationRecord(
        paper=PaperMetadata(title="First", arxiv_id="2401.00001"),
        record_id="rec-001",
    )
    second = RecommendationRecord(
        paper=PaperMetadata(title="Second", arxiv_id="2401.00002"),
        record_id="rec-002",
    )

    assert select_recommendation_for_feedback([first, second]) == second
    assert (
        select_recommendation_for_feedback([first, second], record_id="rec-001")
        == first
    )
    with pytest.raises(ValueError, match="not found"):
        select_recommendation_for_feedback([first], record_id="missing")
    with pytest.raises(ValueError, match="empty"):
        select_recommendation_for_feedback([])


def test_profile_from_feedback_infers_lightweight_preferences() -> None:
    recommendations = [
        RecommendationRecord(
            paper=PaperMetadata(title="Chem Paper", arxiv_id="2401.00001"),
            record_id="rec-001",
            user_requirements="方向: Chemistry + AI；细分方向: molecular dynamics",
        ),
        RecommendationRecord(
            paper=PaperMetadata(title="Math Paper", arxiv_id="2401.00002"),
            record_id="rec-002",
            user_requirements="方向: Math + AI；细分方向: theorem proving",
        ),
    ]
    feedback_records = [
        FeedbackRecord(
            paper_usefulness=5,
            explanation_quality=3,
            recommendation_id="rec-001",
            wanted_more_math=True,
            note="公式讲得还可以更细",
        ),
        FeedbackRecord(
            paper_usefulness=2,
            explanation_quality=4,
            recommendation_id="rec-002",
        ),
    ]

    profile = profile_from_feedback(
        feedback_records,
        recommendations=recommendations,
        existing_profile=ReaderProfile(preferred_fields=["Existing Field"]),
    )
    summary = summarize_feedback(feedback_records, recommendations=recommendations)

    assert profile.preferred_fields == ["Chemistry + AI"]
    assert profile.explanation_style == "more_math"
    assert "多讲数学定义和推导" in profile.free_text_preference
    assert "近期备注" in profile.free_text_preference
    assert profile.extra["feedback_summary"]["total_count"] == 2
    assert summary.average_paper_usefulness == 3.5
    assert feedback_summary_lines(profile)[0].startswith("反馈样本: 2 条")


def test_tied_explanation_style_stays_balanced() -> None:
    profile = profile_from_feedback(
        [
            FeedbackRecord(
                paper_usefulness=5,
                explanation_quality=4,
                wanted_more_math=True,
                wanted_more_code_reproducibility=True,
            )
        ]
    )

    assert profile.explanation_style == "balanced"
    assert "多讲数学定义和推导" in profile.free_text_preference
    assert "多讲代码和可复现性" in profile.free_text_preference
