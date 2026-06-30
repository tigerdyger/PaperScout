from paperscout.analysis.explainer import generate_explanation_report
from paperscout.analysis.llm_explainer import (
    build_llm_explanation_messages,
    generate_llm_explanation_report,
    render_evidence_digest,
)
from paperscout.analysis.materials import (
    MaterialChunk,
    MaterialDocument,
    MaterialIssue,
    MaterialSection,
    PreparedMaterials,
)
from paperscout.llm.client import LLMResponse
from paperscout.storage.schemas import PaperMetadata


def test_render_evidence_digest_contains_evidence_and_gaps() -> None:
    report = generate_explanation_report(
        _prepared_materials(),
        requirements="Chemistry + AI",
        generated_at="2026-06-30T00:00:00+00:00",
    )

    digest = render_evidence_digest(report)

    assert "PaperScout 证据摘要" in digest
    assert "Evidence Rich Paper" in digest
    assert "数学定义和推导" in digest
    assert "formula layout may be incomplete" in digest


def test_build_llm_explanation_messages_truncates_long_digest() -> None:
    report = generate_explanation_report(
        _prepared_materials(),
        generated_at="2026-06-30T00:00:00+00:00",
    )

    messages = build_llm_explanation_messages(report, max_prompt_chars=500)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "已截断" in messages[1]["content"]


def test_generate_llm_explanation_report_wraps_response() -> None:
    report = generate_explanation_report(
        _prepared_materials(),
        generated_at="2026-06-30T00:00:00+00:00",
    )

    class FakeClient:
        def create_chat_completion(self, messages):
            assert len(messages) == 2
            return LLMResponse(
                content="## 一段话总结\n这是模型生成的讲解。",
                model="Qwen/test-model",
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                response_id="resp-1",
            )

    result = generate_llm_explanation_report(report, FakeClient())

    assert result.model == "Qwen/test-model"
    assert result.prompt_chars > 0
    assert "由 LLM 基于 PaperScout 本地证据抽取结果生成" in result.markdown
    assert "prompt_tokens=10" in result.markdown
    assert "这是模型生成的讲解" in result.markdown


def _prepared_materials() -> PreparedMaterials:
    methods = (
        "The method uses an energy equation and a loss objective for molecular "
        "dynamics force fields."
    )
    experiments = (
        "Experiments compare baseline models on benchmark datasets with "
        "ablation studies and reported performance improvements."
    )
    si_text = (
        "The implementation lists hyperparameters. However, the model fails on "
        "out-of-distribution molecules."
    )
    return PreparedMaterials(
        paper=PaperMetadata(
            title="Evidence Rich Paper",
            arxiv_id="2401.00001",
        ),
        documents=[
            MaterialDocument(
                material_id="paper",
                kind="paper",
                status="parsed",
                file_type="text",
                text_char_count=len(methods) + len(experiments),
                sections=[
                    MaterialSection(
                        material_id="paper",
                        name="Methods",
                        text=methods,
                    ),
                    MaterialSection(
                        material_id="paper",
                        name="Experiments",
                        text=experiments,
                    ),
                ],
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
                text_char_count=len(si_text),
                sections=[
                    MaterialSection(
                        material_id="supplementary",
                        name="Supplementary Information",
                        text=si_text,
                    )
                ],
            ),
        ],
        chunks=[
            MaterialChunk(
                chunk_id="paper_chunk_1",
                material_id="paper",
                kind="paper",
                section_name="Methods",
                text=methods,
                char_count=len(methods),
            ),
            MaterialChunk(
                chunk_id="paper_chunk_2",
                material_id="paper",
                kind="paper",
                section_name="Experiments",
                text=experiments,
                char_count=len(experiments),
            ),
            MaterialChunk(
                chunk_id="supplementary_chunk_1",
                material_id="supplementary",
                kind="supplementary",
                section_name="Supplementary Information",
                text=si_text,
                char_count=len(si_text),
            ),
        ],
        issues=[
            MaterialIssue(
                code="pdf_text_extraction_warning",
                material_id="paper",
                message="formula layout may be incomplete",
            )
        ],
    )
