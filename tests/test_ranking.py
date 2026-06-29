import math

import pytest

from paperscout.collectors.manual import ManualCandidate
from paperscout.ranking.scorer import load_ranking_config, score_candidate
from paperscout.recommender.select import select_best_candidate
from paperscout.storage.schemas import PaperMetadata, RecommendationRecord


def test_score_candidate_uses_log_counts_and_reports_missing_signals() -> None:
    candidate = ManualCandidate(
        paper=PaperMetadata(title="Scored candidate", arxiv_id="2401.00002"),
        attention={
            "recent_citation_count": 9,
            "github_stars": 99,
            "paper_with_code_has_entry": "true",
            "source_confidence": 0.5,
        },
        requirement_match_score=2.0,
    )

    scored = score_candidate(candidate)

    assert scored.score.components["requirement_match_score"] == 2.0
    assert scored.score.components["recent_attention_score"] == pytest.approx(
        2.0 * (math.log1p(9) / math.log1p(25)) / 2.7
    )
    assert scored.score.components["reproducibility_signal_score"] == 1.0
    assert scored.score.components["lifetime_attention_score"] == pytest.approx(
        0.5 * (0.7 * math.log1p(99) / math.log1p(500)) / 2.2
    )
    assert scored.score.components["source_confidence_score"] == 0.4
    assert "github_recent_commits" in scored.score.missing_signals
    assert "github_repository_present" not in scored.score.missing_signals
    assert "missing signals add no positive evidence" in scored.score.notes[-1]


def test_score_candidate_rejects_invalid_attention_values() -> None:
    with pytest.raises(ValueError, match="recent_citation_count"):
        score_candidate(
            ManualCandidate(
                paper=PaperMetadata(title="Bad count"),
                attention={"recent_citation_count": -1},
            )
        )

    with pytest.raises(ValueError, match="paper_with_code_has_entry"):
        score_candidate(
            ManualCandidate(
                paper=PaperMetadata(title="Bad boolean"),
                attention={"paper_with_code_has_entry": "maybe"},
            )
        )


def test_load_ranking_config(tmp_path) -> None:
    path = tmp_path / "ranking.json"
    path.write_text(
        """
        {
          "group_weights": {
            "requirement_match_score": 1.0,
            "source_confidence_score": 2.0,
            "low_confidence_penalty": 0.0
          },
          "signal_groups": {
            "source_confidence_score": {
              "source_confidence": 1.0
            }
          },
          "count_signals": [],
          "boolean_signals": [],
          "bounded_signals": ["source_confidence"],
          "missing_signal_names": ["source_confidence"]
        }
        """,
        encoding="utf-8",
    )

    config = load_ranking_config(path)
    scored = score_candidate(
        ManualCandidate(
            paper=PaperMetadata(title="Configured"),
            attention={"source_confidence": 0.5},
            requirement_match_score=1.0,
        ),
        config=config,
    )

    assert scored.score.total == 2.0
    assert scored.score.missing_signals == []


def test_recent_attention_outweighs_lifetime_attention() -> None:
    recent = score_candidate(
        ManualCandidate(
            paper=PaperMetadata(title="Recent attention"),
            attention={"recent_citation_count": 25, "source_confidence": 0.8},
        )
    )
    historical = score_candidate(
        ManualCandidate(
            paper=PaperMetadata(title="Historical attention"),
            attention={
                "github_stars": 500,
                "semantic_scholar_citation_count": 500,
                "source_confidence": 0.8,
            },
        )
    )

    assert recent.score.components["recent_attention_score"] > (
        historical.score.components["lifetime_attention_score"]
    )
    assert recent.score.total > historical.score.total


def test_low_confidence_penalty_is_explicit() -> None:
    scored = score_candidate(
        ManualCandidate(
            paper=PaperMetadata(title="Low confidence"),
            attention={"source_confidence": 0.2},
        )
    )

    assert scored.score.components["source_confidence_score"] == pytest.approx(0.16)
    assert scored.score.components["low_confidence_penalty"] == pytest.approx(-0.15)


def test_select_best_candidate_skips_duplicate_history() -> None:
    duplicate = ManualCandidate(
        paper=PaperMetadata(title="Already recommended", arxiv_id="2401.00001"),
        attention={
            "recent_citation_count": 999,
            "github_stars": 9999,
            "source_confidence": 1.0,
        },
        requirement_match_score=5.0,
    )
    selected = ManualCandidate(
        paper=PaperMetadata(title="Strong non duplicate", arxiv_id="2401.00002"),
        attention={
            "recent_citation_count": 35,
            "github_stars": 250,
            "github_recent_commits": 12,
            "paper_with_code_has_entry": True,
            "source_confidence": 0.9,
        },
        requirement_match_score=2.0,
    )
    lower_by_attention = ManualCandidate(
        paper=PaperMetadata(title="Lower attention", arxiv_id="2401.00003"),
        attention={
            "recent_citation_count": 2,
            "github_stars": 5,
            "source_confidence": 0.7,
        },
        requirement_match_score=1.0,
    )
    lower_by_match = ManualCandidate(
        paper=PaperMetadata(title="Poor match", arxiv_id="2401.00004"),
        attention={
            "recent_citation_count": 20,
            "github_stars": 20,
            "source_confidence": 0.8,
        },
        requirement_match_score=0.0,
    )
    missing_signals = ManualCandidate(
        paper=PaperMetadata(title="Sparse metadata", arxiv_id="2401.00005"),
        attention={"source_confidence": 0.4},
        requirement_match_score=1.5,
    )
    previous = [
        RecommendationRecord(
            paper=PaperMetadata(title="Old title", arxiv_id="https://arxiv.org/abs/2401.00001")
        )
    ]

    result = select_best_candidate(
        [
            duplicate,
            lower_by_attention,
            missing_signals,
            selected,
            lower_by_match,
        ],
        previous_recommendations=previous,
    )

    assert result.selected is not None
    assert result.selected.paper.title == "Strong non duplicate"
    assert len(result.ranked_candidates) == 4
    assert len(result.skipped_duplicates) == 1
    assert result.skipped_duplicates[0].paper.title == "Already recommended"
    assert result.ranked_candidates[0].score.total >= result.ranked_candidates[1].score.total


def test_select_best_candidate_returns_none_when_all_candidates_are_duplicates() -> None:
    candidate = ManualCandidate(
        paper=PaperMetadata(title="Only candidate", doi="10.1000/only"),
        attention={"source_confidence": 1.0},
    )
    previous = [
        RecommendationRecord(
            paper=PaperMetadata(title="Only candidate old", doi="10.1000/only")
        )
    ]

    result = select_best_candidate([candidate], previous_recommendations=previous)

    assert result.selected is None
    assert result.ranked_candidates == []
    assert len(result.skipped_duplicates) == 1
