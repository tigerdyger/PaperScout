import json

import pytest

from paperscout.storage.jsonl_store import (
    append_feedback,
    append_recommendation,
    find_duplicate_recommendation,
    has_recommended_paper,
    load_feedback,
    load_profile,
    load_recommendations,
    read_jsonl,
    save_profile,
)
from paperscout.storage.schemas import (
    FeedbackRecord,
    PaperMetadata,
    ReaderProfile,
    RecommendationRecord,
    ScoreBreakdown,
)


def test_recommendation_jsonl_round_trip_and_duplicate_detection(tmp_path) -> None:
    history_path = tmp_path / "history" / "recommendations.jsonl"
    record = RecommendationRecord(
        paper=PaperMetadata(
            title="Graph Networks as Learnable Physics Engines",
            arxiv_id="1806.01242",
            doi="10.48550/arXiv.1806.01242",
        ),
        user_requirements="AI4S",
        score=ScoreBreakdown(
            total=4.5,
            components={"recent_attention": 3.0, "confidence": 1.5},
        ),
        record_id="rec-001",
    )

    append_recommendation(history_path, record)
    loaded = load_recommendations(history_path)
    candidate = PaperMetadata(
        title="Different title from another source",
        arxiv_id="https://arxiv.org/abs/1806.01242",
    )

    assert len(loaded) == 1
    assert loaded[0].paper.title == "Graph Networks as Learnable Physics Engines"
    assert loaded[0].score.components["recent_attention"] == 3.0
    assert has_recommended_paper(candidate, loaded)
    assert find_duplicate_recommendation(candidate, loaded).record_id == "rec-001"


def test_missing_jsonl_file_is_empty(tmp_path) -> None:
    assert read_jsonl(tmp_path / "missing.jsonl") == []
    assert load_recommendations(tmp_path / "missing.jsonl") == []


def test_feedback_jsonl_round_trip(tmp_path) -> None:
    feedback_path = tmp_path / "history" / "feedback.jsonl"
    feedback = FeedbackRecord(
        paper_usefulness=5,
        explanation_quality=4,
        recommendation_id="rec-001",
        paper_identifiers=["arxiv:1806.01242"],
        paper_title="Graph Networks as Learnable Physics Engines",
        wanted_more_math=True,
        note="数学推导可以更多一点",
    )

    append_feedback(feedback_path, feedback)
    loaded = load_feedback(feedback_path)

    assert len(loaded) == 1
    assert loaded[0].paper_usefulness == 5
    assert loaded[0].wanted_more_math is True
    assert loaded[0].note == "数学推导可以更多一点"


def test_profile_json_round_trip_and_missing_profile(tmp_path) -> None:
    profile_path = tmp_path / "history" / "profile.json"

    assert load_profile(profile_path) is None

    save_profile(
        profile_path,
        ReaderProfile(
            preferred_fields=["CS-AI", " Chemistry + AI4S "],
            free_text_preference="希望多讲实验设计",
            explanation_style="more_experiments",
        ),
    )
    loaded = load_profile(profile_path)

    assert loaded is not None
    assert loaded.preferred_fields == ["CS-AI", "Chemistry + AI4S"]
    assert loaded.free_text_preference == "希望多讲实验设计"
    assert loaded.explanation_style == "more_experiments"


def test_bad_jsonl_reports_line_number(tmp_path) -> None:
    broken_path = tmp_path / "broken.jsonl"
    broken_path.write_text(json.dumps({"ok": True}) + "\nnot-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        read_jsonl(broken_path)
