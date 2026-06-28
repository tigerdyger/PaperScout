import json
from io import StringIO
from types import SimpleNamespace

from paperscout.interfaces.cli import main, run_recommend
from paperscout.storage.jsonl_store import (
    append_recommendation,
    load_recommendations,
    save_profile,
)
from paperscout.storage.schemas import PaperMetadata, ReaderProfile, RecommendationRecord


def test_recommend_command_prompts_and_saves_recommendation(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    history_path = tmp_path / "history" / "recommendations.jsonl"
    output = StringIO()
    candidates_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "paper": {
                            "title": "Candidate A",
                            "arxiv_id": "2401.00001",
                        },
                        "attention": {
                            "recent_citation_count": 30,
                            "github_stars": 200,
                            "github_recent_commits": 4,
                            "paper_with_code_has_entry": True,
                            "source_confidence": 0.9,
                        },
                        "requirement_match_score": 2.0,
                    },
                    {
                        "paper": {
                            "title": "Candidate B",
                            "arxiv_id": "2401.00002",
                        },
                        "attention": {
                            "recent_citation_count": 1,
                            "source_confidence": 0.5,
                        },
                        "requirement_match_score": 0.5,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        candidates=candidates_path,
        ranking_config=tmp_path / "missing-ranking.json",
        history=history_path,
        profile=tmp_path / "missing-profile.json",
        requirements=None,
        report_path="reports/candidate-a.md",
        record_id="rec-001",
        show_top=2,
    )

    exit_code = run_recommend(
        args,
        input_fn=lambda prompt: "",
        output=output,
    )
    records = load_recommendations(history_path)

    assert exit_code == 0
    assert len(records) == 1
    assert records[0].paper.title == "Candidate A"
    assert records[0].user_requirements == "no_extra_constraints"
    assert records[0].record_id == "rec-001"
    assert records[0].report_path == "reports/candidate-a.md"
    text = output.getvalue()
    assert "本次需求: no_extra_constraints" in text
    assert "推荐论文: Candidate A" in text
    assert "已保存推荐记录" in text


def test_recommend_command_uses_profile_and_skips_duplicate(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    history_path = tmp_path / "history" / "recommendations.jsonl"
    profile_path = tmp_path / "history" / "profile.json"
    output = StringIO()
    append_recommendation(
        history_path,
        RecommendationRecord(
            paper=PaperMetadata(title="Old Candidate", arxiv_id="2401.00001")
        ),
    )
    save_profile(
        profile_path,
        ReaderProfile(
            preferred_fields=["Chemistry + AI4S"],
            free_text_preference="多讲实验设计",
            explanation_style="more_experiments",
        ),
    )
    candidates_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "paper": {
                            "title": "Duplicate Candidate",
                            "arxiv_id": "https://arxiv.org/abs/2401.00001",
                        },
                        "attention": {
                            "recent_citation_count": 1000,
                            "source_confidence": 1.0,
                        },
                        "requirement_match_score": 5.0,
                    },
                    {
                        "paper": {
                            "title": "Fresh Candidate",
                            "arxiv_id": "2401.00003",
                        },
                        "attention": {
                            "recent_citation_count": 10,
                            "source_confidence": 0.8,
                        },
                        "requirement_match_score": 1.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        candidates=candidates_path,
        ranking_config=tmp_path / "missing-ranking.json",
        history=history_path,
        profile=profile_path,
        requirements="AI4S chemistry",
        report_path=None,
        record_id="rec-002",
        show_top=3,
    )

    exit_code = run_recommend(args, output=output)
    records = load_recommendations(history_path)

    assert exit_code == 0
    assert len(records) == 2
    assert records[-1].paper.title == "Fresh Candidate"
    assert records[-1].extra["profile"]["preferred_fields"] == ["Chemistry + AI4S"]
    text = output.getvalue()
    assert "本地偏好方向: Chemistry + AI4S" in text
    assert "跳过重复候选: 1" in text


def test_recommend_command_returns_error_when_every_candidate_is_duplicate(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    history_path = tmp_path / "history" / "recommendations.jsonl"
    output = StringIO()
    append_recommendation(
        history_path,
        RecommendationRecord(
            paper=PaperMetadata(title="Already seen", doi="10.1000/seen")
        ),
    )
    candidates_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "paper": {
                            "title": "Already seen again",
                            "doi": "https://doi.org/10.1000/seen",
                        },
                        "attention": {"source_confidence": 1.0},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        candidates=candidates_path,
        ranking_config=tmp_path / "missing-ranking.json",
        history=history_path,
        profile=tmp_path / "missing-profile.json",
        requirements="CS-AI",
        report_path=None,
        record_id=None,
        show_top=3,
    )

    exit_code = run_recommend(args, output=output)

    assert exit_code == 1
    assert "没有可推荐的非重复候选论文" in output.getvalue()
    assert len(load_recommendations(history_path)) == 1


def test_main_recommend_command(monkeypatch, tmp_path, capsys) -> None:
    candidates_path = tmp_path / "candidates.json"
    history_path = tmp_path / "history" / "recommendations.jsonl"
    candidates_path.write_text(
        json.dumps(
            [
                {
                    "paper": {
                        "title": "Main candidate",
                        "url": "https://example.org/main-candidate",
                    },
                    "attention": {"source_confidence": 0.7},
                }
            ]
        ),
        encoding="utf-8",
    )
    answers = iter(["2", "1", "3,5", "不要纯 benchmark"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    exit_code = main(
        [
            "recommend",
            "--candidates",
            str(candidates_path),
            "--history",
            str(history_path),
            "--ranking-config",
            str(tmp_path / "missing-ranking.json"),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Economics / Finance + AI" in output
    assert "本次需求: 方向: Math + AI" in output
    assert "细分方向: theorem proving" in output
    assert "多讲数学定义和推导" in output
    assert "多讲局限性和失败模式" in output
    records = load_recommendations(history_path)
    assert records[0].paper.title == "Main candidate"
    assert records[0].user_requirements == (
        "方向: Math + AI；"
        "细分方向: theorem proving；"
        "讲解偏好: 多讲数学定义和推导, 多讲局限性和失败模式；"
        "补充: 不要纯 benchmark"
    )


def test_guided_requirements_allows_no_extra_constraints(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    history_path = tmp_path / "history" / "recommendations.jsonl"
    output = StringIO()
    candidates_path.write_text(
        json.dumps(
            [
                {
                    "paper": {
                        "title": "No constraint candidate",
                        "url": "https://example.org/no-constraint",
                    },
                    "attention": {"source_confidence": 0.7},
                }
            ]
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        candidates=candidates_path,
        ranking_config=tmp_path / "missing-ranking.json",
        history=history_path,
        profile=tmp_path / "missing-profile.json",
        requirements=None,
        report_path=None,
        record_id=None,
        show_top=1,
    )

    exit_code = run_recommend(
        args,
        input_fn=lambda prompt: "",
        output=output,
    )

    assert exit_code == 0
    assert "Economics / Finance + AI" in output.getvalue()
    assert load_recommendations(history_path)[0].user_requirements == (
        "no_extra_constraints"
    )
