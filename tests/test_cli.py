import json
from io import StringIO
from types import SimpleNamespace

from paperscout.analysis.materials import (
    MaterialChunk,
    MaterialDocument,
    MaterialIssue,
    MaterialSection,
    PreparedMaterials,
)
from paperscout.collectors.github import GitHubRepository
from paperscout.collectors.manual import ManualCandidate, load_manual_candidates
from paperscout.interfaces import cli
from paperscout.interfaces.cli import (
    main,
    run_collect,
    run_explain,
    run_prepare_materials,
    run_recommend,
)
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


def test_collect_command_writes_merged_candidates(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "candidates.generated.json"

    def fake_search_arxiv(query, max_results, refresh):
        assert query == "AI chemistry"
        assert max_results == 3
        assert refresh is True
        return [
            ManualCandidate(
                paper=PaperMetadata(
                    title="arXiv candidate",
                    arxiv_id="2401.00001",
                    extra={"github_url": "https://github.com/owner/repo"},
                ),
                attention={"source_confidence": 0.7},
            )
        ]

    def fake_search_semantic_scholar(query, limit, require_api_key, refresh):
        assert query == "AI chemistry"
        assert limit == 3
        assert require_api_key is True
        assert refresh is True
        return [
            ManualCandidate(
                paper=PaperMetadata(
                    title="Semantic Scholar candidate",
                    arxiv_id="2401.00001",
                    semantic_scholar_id="abc123",
                ),
                attention={
                    "source_confidence": 0.8,
                    "semantic_scholar_citation_count": 20,
                },
            )
        ]

    def fake_search_github_repositories(
        query, max_results, require_token, refresh
    ):
        assert query == "owner repo"
        assert max_results == 2
        assert require_token is True
        assert refresh is True
        return [
            GitHubRepository(
                full_name="owner/repo",
                html_url="https://github.com/owner/repo",
                stars=99,
            )
        ]

    monkeypatch.setattr(cli, "search_arxiv", fake_search_arxiv)
    monkeypatch.setattr(
        cli,
        "search_semantic_scholar",
        fake_search_semantic_scholar,
    )
    monkeypatch.setattr(
        cli,
        "search_github_repositories",
        fake_search_github_repositories,
    )
    args = SimpleNamespace(
        query="AI chemistry",
        output=output_path,
        source=["arxiv", "semantic-scholar"],
        max_results=3,
        refresh=True,
        require_api_keys=True,
        github_query="owner repo",
        github_max_results=2,
    )

    exit_code = run_collect(args)
    candidates = load_manual_candidates(output_path)

    assert exit_code == 0
    assert len(candidates) == 1
    assert candidates[0].paper.semantic_scholar_id == "abc123"
    assert candidates[0].attention["source_confidence"] == 0.8
    assert candidates[0].attention["semantic_scholar_citation_count"] == 20
    assert candidates[0].attention["github_stars"] == 99


def test_collect_command_defaults_to_arxiv(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "candidates.generated.json"

    def fake_search_arxiv(query, max_results, refresh):
        return [
            ManualCandidate(
                paper=PaperMetadata(title="Default arXiv", arxiv_id="2401.00003"),
                attention={"source_confidence": 0.7},
            )
        ]

    monkeypatch.setattr(cli, "search_arxiv", fake_search_arxiv)
    args = SimpleNamespace(
        query="AI",
        output=output_path,
        source=None,
        max_results=10,
        refresh=False,
        require_api_keys=False,
        github_query=None,
        github_max_results=5,
    )

    exit_code = run_collect(args)
    candidates = load_manual_candidates(output_path)

    assert exit_code == 0
    assert len(candidates) == 1
    assert candidates[0].paper.title == "Default arXiv"


def test_collect_command_fetches_explicit_github_repository(
    monkeypatch,
    tmp_path,
) -> None:
    output_path = tmp_path / "candidates.generated.json"

    def fake_search_arxiv(query, max_results, refresh):
        return [
            ManualCandidate(
                paper=PaperMetadata(
                    title="Explicit code",
                    arxiv_id="2401.00004",
                    extra={"github_url": "https://github.com/owner/repo"},
                ),
                attention={"source_confidence": 0.7},
            )
        ]

    def fake_search_github_repositories(
        query, max_results, require_token, refresh
    ):
        return []

    def fake_fetch_github_repository(full_name, require_token, refresh):
        assert full_name == "owner/repo"
        return GitHubRepository(
            full_name="owner/repo",
            html_url="https://github.com/owner/repo",
            stars=14,
        )

    monkeypatch.setattr(cli, "search_arxiv", fake_search_arxiv)
    monkeypatch.setattr(
        cli,
        "search_github_repositories",
        fake_search_github_repositories,
    )
    monkeypatch.setattr(cli, "fetch_github_repository", fake_fetch_github_repository)
    args = SimpleNamespace(
        query="AI",
        output=output_path,
        source=["arxiv"],
        max_results=10,
        refresh=False,
        require_api_keys=False,
        github_query="owner repo",
        github_max_results=5,
    )

    exit_code = run_collect(args)
    candidates = load_manual_candidates(output_path)

    assert exit_code == 0
    assert candidates[0].attention["github_stars"] == 14
    assert candidates[0].paper.extra["github_repository"]["full_name"] == "owner/repo"


def test_collect_command_returns_clean_error_for_collector_failure(
    monkeypatch,
    tmp_path,
) -> None:
    output_path = tmp_path / "candidates.generated.json"
    output = StringIO()

    def fake_search_semantic_scholar(query, limit, require_api_key, refresh):
        raise RuntimeError("SEMANTIC_SCHOLAR_API_KEY is required.")

    monkeypatch.setattr(
        cli,
        "search_semantic_scholar",
        fake_search_semantic_scholar,
    )
    args = SimpleNamespace(
        query="AI chemistry",
        output=output_path,
        source=["semantic-scholar"],
        max_results=10,
        refresh=False,
        require_api_keys=True,
        github_query=None,
        github_max_results=5,
    )

    exit_code = run_collect(args, output=output)

    assert exit_code == 1
    assert "采集失败: SEMANTIC_SCHOLAR_API_KEY is required." in output.getvalue()
    assert not output_path.exists()


def test_prepare_materials_command_prints_summary(monkeypatch, tmp_path) -> None:
    output = StringIO()

    def fake_prepare_materials(
        paper,
        paper_pdf,
        supplementary,
        cache_dir,
        refresh,
        max_chunk_chars,
    ):
        assert paper.title == "Material Paper"
        assert paper.arxiv_id == "2401.00001"
        assert paper_pdf == "paper.pdf"
        assert supplementary == "si.txt"
        assert cache_dir == tmp_path / "cache"
        assert refresh is True
        assert max_chunk_chars == 123
        return PreparedMaterials(
            paper=paper,
            cache_path=str(tmp_path / "cache" / "parsed.json"),
            documents=[
                MaterialDocument(
                    material_id="paper",
                    kind="paper",
                    status="parsed",
                    file_type="pdf",
                    text_char_count=300,
                    sections=[
                        MaterialSection(
                            material_id="paper",
                            name="Methods",
                            text="method text",
                        )
                    ],
                )
            ],
            chunks=[
                MaterialChunk(
                    chunk_id="paper_chunk_1",
                    material_id="paper",
                    kind="paper",
                    section_name="Methods",
                    text="method text",
                    char_count=11,
                )
            ],
            issues=[
                MaterialIssue(
                    code="pdf_text_extraction_warning",
                    material_id="paper",
                    message="layout loss",
                )
            ],
        )

    monkeypatch.setattr(cli, "prepare_materials", fake_prepare_materials)
    args = SimpleNamespace(
        title="Material Paper",
        doi=None,
        arxiv_id="2401.00001",
        url=None,
        pdf="paper.pdf",
        si="si.txt",
        cache_dir=tmp_path / "cache",
        refresh=True,
        max_chunk_chars=123,
    )

    exit_code = run_prepare_materials(args, output=output)

    assert exit_code == 0
    text = output.getvalue()
    assert "materials cache:" in text
    assert "- paper: parsed, type=pdf, sections=1, chars=300" in text
    assert "chunks: 1" in text
    assert "warning paper: pdf_text_extraction_warning: layout loss" in text


def test_explain_command_writes_markdown_report(tmp_path) -> None:
    materials_path = tmp_path / "materials.json"
    report_path = tmp_path / "report.md"
    output = StringIO()
    prepared = PreparedMaterials(
        paper=PaperMetadata(title="CLI Explain Paper", arxiv_id="2401.00009"),
        documents=[
            MaterialDocument(
                material_id="paper",
                kind="paper",
                status="parsed",
                file_type="text",
                text_char_count=160,
                sections=[
                    MaterialSection(
                        material_id="paper",
                        name="Methods",
                        text=(
                            "The method uses a loss objective and an energy "
                            "equation for molecular dynamics force fields."
                        ),
                    )
                ],
            )
        ],
        chunks=[
            MaterialChunk(
                chunk_id="paper_chunk_1",
                material_id="paper",
                kind="paper",
                section_name="Methods",
                text=(
                    "The method uses a loss objective and an energy equation "
                    "for molecular dynamics force fields."
                ),
                char_count=94,
            )
        ],
    )
    materials_path.write_text(
        json.dumps(prepared.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        materials=materials_path,
        output=report_path,
        requirements="Chemistry + AI; more math",
        max_snippets=1,
    )

    exit_code = run_explain(args, output=output)

    assert exit_code == 0
    assert report_path.exists()
    assert "report:" in output.getvalue()
    assert "sections:" in output.getvalue()
    assert "数学定义和推导" in report_path.read_text(encoding="utf-8")


def test_explain_command_rejects_invalid_snippet_count(tmp_path) -> None:
    output = StringIO()
    args = SimpleNamespace(
        materials=tmp_path / "missing.json",
        output=None,
        requirements=None,
        max_snippets=0,
    )

    exit_code = run_explain(args, output=output)

    assert exit_code == 1
    assert "positive integer" in output.getvalue()
