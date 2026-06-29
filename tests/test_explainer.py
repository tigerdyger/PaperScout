import json

from paperscout.analysis.explainer import (
    collect_evidence,
    generate_explanation_report,
    write_explanation_report,
)
from paperscout.analysis.materials import (
    MaterialChunk,
    MaterialDocument,
    MaterialIssue,
    MaterialSection,
    PreparedMaterials,
)
from paperscout.storage.schemas import PaperMetadata


def test_generate_explanation_report_contains_required_sections_and_evidence() -> None:
    report = generate_explanation_report(
        _prepared_materials(),
        requirements="Chemistry + AI; molecular dynamics; more math",
        max_snippets_per_section=2,
        generated_at="2026-06-29T00:00:00+00:00",
    )

    titles = {section.title for section in report.sections}
    markdown = report.to_markdown()

    assert "为什么推荐这篇论文" in titles
    assert "方法或算法" in titles
    assert "数学定义和推导" in titles
    assert "实验设计" in titles
    assert "可复现性检查" in titles
    assert "不能视为 PaperScout 已独立核查论文结论" in markdown
    assert "证据片段：" in markdown
    assert "pdf_text_extraction_warning" in markdown
    assert any(
        section.key == "math_derivation" and section.evidence
        for section in report.sections
    )


def test_generate_explanation_report_marks_missing_evidence() -> None:
    materials = PreparedMaterials(
        paper=PaperMetadata(title="Sparse Paper"),
        documents=[
            MaterialDocument(
                material_id="paper",
                kind="paper",
                status="parsed",
                sections=[
                    MaterialSection(
                        material_id="paper",
                        name="Abstract",
                        text="This paper studies a broad scientific problem.",
                    )
                ],
            )
        ],
        chunks=[
            MaterialChunk(
                chunk_id="paper_chunk_1",
                material_id="paper",
                kind="paper",
                section_name="Abstract",
                text="This paper studies a broad scientific problem.",
                char_count=46,
            )
        ],
    )

    report = generate_explanation_report(materials, generated_at="2026-06-29T00:00:00+00:00")
    math_section = next(section for section in report.sections if section.key == "math_derivation")

    assert math_section.status == "missing"
    assert "没有提供足够明确的证据" in math_section.body
    assert "数学定义和推导" in report.to_markdown()


def test_requirements_do_not_create_section_evidence_without_section_terms() -> None:
    materials = PreparedMaterials(
        paper=PaperMetadata(title="Domain Only Paper"),
        documents=[
            MaterialDocument(
                material_id="paper",
                kind="paper",
                status="parsed",
                sections=[
                    MaterialSection(
                        material_id="paper",
                        name="Abstract",
                        text="Molecular dynamics force fields for chemistry.",
                    )
                ],
            )
        ],
        chunks=[
            MaterialChunk(
                chunk_id="paper_chunk_1",
                material_id="paper",
                kind="paper",
                section_name="Abstract",
                text="Molecular dynamics force fields for chemistry.",
                char_count=47,
            )
        ],
    )

    report = generate_explanation_report(
        materials,
        requirements="Chemistry + AI; molecular dynamics; force fields",
    )
    baseline_section = next(
        section for section in report.sections if section.key == "baselines_and_ablations"
    )

    assert baseline_section.status == "missing"
    assert not baseline_section.evidence


def test_write_explanation_report_uses_stable_default_path(tmp_path) -> None:
    report = generate_explanation_report(
        _prepared_materials(),
        generated_at="2026-06-29T00:00:00+00:00",
    )

    output_path = write_explanation_report(report, reports_dir=tmp_path / "reports")

    assert output_path.name == "2026-06-29-evidence-rich-paper.md"
    assert report.report_path == str(output_path)
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("# Evidence Rich Paper")


def test_collect_evidence_prioritizes_specific_matches() -> None:
    chunks = [
        MaterialChunk(
            chunk_id="paper_chunk_1",
            material_id="paper",
            kind="paper",
            section_name="Introduction",
            text="The method is introduced at a high level.",
            char_count=42,
        ),
        MaterialChunk(
            chunk_id="paper_chunk_2",
            material_id="paper",
            kind="paper",
            section_name="Methods",
            text="The method optimizes a loss objective with an energy equation.",
            char_count=61,
        ),
    ]

    evidence = collect_evidence(chunks, ["method", "loss", "objective", "equation"])

    assert evidence[0].chunk_id == "paper_chunk_2"
    assert evidence[0].matched_terms == ["method", "loss", "objective", "equation"]


def test_prepared_materials_round_trip_supports_explainer_input(tmp_path) -> None:
    materials = _prepared_materials()
    path = tmp_path / "materials.json"
    path.write_text(
        json.dumps(materials.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )

    restored = PreparedMaterials.from_dict(json.loads(path.read_text(encoding="utf-8")))
    report = generate_explanation_report(restored)

    assert report.materials.paper.title == "Evidence Rich Paper"
    assert report.sections


def _prepared_materials() -> PreparedMaterials:
    paper_sections = [
        MaterialSection(
            material_id="paper",
            name="Abstract",
            text=(
                "This paper proposes a molecular dynamics force field model for "
                "chemistry and presents the main contribution."
            ),
        ),
        MaterialSection(
            material_id="paper",
            name="Methods",
            text=(
                "The method uses an energy equation E_theta and a loss objective "
                "combining force loss and energy loss. Algorithm 1 describes "
                "training and inference."
            ),
        ),
        MaterialSection(
            material_id="paper",
            name="Experiments",
            text=(
                "Experiments evaluate benchmark datasets with baseline models, "
                "ablation studies, MAE and RMSE metrics, validation splits, and "
                "reported performance improvements."
            ),
        ),
    ]
    supplementary_sections = [
        MaterialSection(
            material_id="supplementary",
            name="Supplementary Information",
            text=(
                "The implementation is available on GitHub with hyperparameter "
                "details. However, the model fails on out-of-distribution "
                "molecules and assumes fixed charge states."
            ),
        )
    ]
    chunks = [
        MaterialChunk(
            chunk_id="paper_chunk_1",
            material_id="paper",
            kind="paper",
            section_name="Abstract",
            text=paper_sections[0].text,
            char_count=len(paper_sections[0].text),
        ),
        MaterialChunk(
            chunk_id="paper_chunk_2",
            material_id="paper",
            kind="paper",
            section_name="Methods",
            text=paper_sections[1].text,
            char_count=len(paper_sections[1].text),
        ),
        MaterialChunk(
            chunk_id="paper_chunk_3",
            material_id="paper",
            kind="paper",
            section_name="Experiments",
            text=paper_sections[2].text,
            char_count=len(paper_sections[2].text),
        ),
        MaterialChunk(
            chunk_id="supplementary_chunk_1",
            material_id="supplementary",
            kind="supplementary",
            section_name="Supplementary Information",
            text=supplementary_sections[0].text,
            char_count=len(supplementary_sections[0].text),
        ),
    ]
    return PreparedMaterials(
        paper=PaperMetadata(
            title="Evidence Rich Paper",
            arxiv_id="2401.00001",
            url="https://arxiv.org/abs/2401.00001",
        ),
        documents=[
            MaterialDocument(
                material_id="paper",
                kind="paper",
                status="parsed",
                file_type="pdf",
                text_char_count=sum(len(section.text) for section in paper_sections),
                sections=paper_sections,
                issues=[
                    MaterialIssue(
                        code="pdf_text_extraction_warning",
                        material_id="paper",
                        message="formula layout may be incomplete",
                    )
                ],
            ),
            MaterialDocument(
                material_id="supplementary",
                kind="supplementary",
                status="parsed",
                file_type="text",
                text_char_count=sum(
                    len(section.text) for section in supplementary_sections
                ),
                sections=supplementary_sections,
            ),
        ],
        chunks=chunks,
        issues=[
            MaterialIssue(
                code="pdf_text_extraction_warning",
                material_id="paper",
                message="formula layout may be incomplete",
            )
        ],
    )
