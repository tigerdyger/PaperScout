import json

import pytest

from paperscout.collectors.manual import (
    ManualCandidate,
    dump_manual_candidates,
    load_manual_candidates,
)
from paperscout.storage.schemas import PaperMetadata


def test_load_manual_candidates_from_object(tmp_path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "paper": {
                            "title": "Manual candidate",
                            "arxiv_id": "2401.00001",
                        },
                        "attention": {"github_stars": 10},
                        "requirement_match_score": 1.25,
                        "notes": [" curated "],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    candidates = load_manual_candidates(path)

    assert len(candidates) == 1
    assert candidates[0].paper.title == "Manual candidate"
    assert candidates[0].paper.arxiv_id == "2401.00001"
    assert candidates[0].attention["github_stars"] == 10
    assert candidates[0].requirement_match_score == 1.25
    assert candidates[0].notes == ["curated"]


def test_load_manual_candidates_from_top_level_list(tmp_path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            [
                {
                    "paper": {
                        "title": "List candidate",
                        "doi": "10.1000/list-candidate",
                    }
                }
            ]
        ),
        encoding="utf-8",
    )

    candidates = load_manual_candidates(path)

    assert len(candidates) == 1
    assert candidates[0].paper.doi == "10.1000/list-candidate"


def test_dump_manual_candidates_round_trip(tmp_path) -> None:
    path = tmp_path / "nested" / "candidates.json"
    original = [
        ManualCandidate(
            paper=PaperMetadata(title="Round trip", url="https://example.org/paper"),
            attention={"source_confidence": 0.7},
            requirement_match_score=2.0,
        )
    ]

    dump_manual_candidates(path, original)
    loaded = load_manual_candidates(path)

    assert len(loaded) == 1
    assert loaded[0].paper.url == "https://example.org/paper"
    assert loaded[0].attention == {"source_confidence": 0.7}
    assert loaded[0].requirement_match_score == 2.0


def test_manual_candidates_reject_non_json_files(tmp_path) -> None:
    path = tmp_path / "candidates.yaml"
    path.write_text("candidates: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON"):
        load_manual_candidates(path)


def test_manual_candidate_requires_paper_object() -> None:
    with pytest.raises(ValueError, match="paper"):
        ManualCandidate.from_dict({"attention": {"github_stars": 10}})
