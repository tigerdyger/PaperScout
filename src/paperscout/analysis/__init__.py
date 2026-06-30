"""Paper and supplementary material analysis."""

from paperscout.analysis.materials import (
    MaterialChunk,
    MaterialDocument,
    MaterialIssue,
    MaterialSection,
    PreparedMaterials,
    build_material_chunks,
    prepare_materials,
    split_text_into_sections,
)
from paperscout.analysis.explainer import (
    EvidenceSnippet,
    ExplanationReport,
    ExplanationSection,
    collect_evidence,
    default_report_path,
    generate_explanation_report,
    load_prepared_materials,
    suggested_questions,
    suggested_reading_order,
    write_explanation_report,
)
from paperscout.analysis.llm_explainer import (
    LLMExplanationResult,
    build_llm_explanation_messages,
    generate_llm_explanation_report,
    render_evidence_digest,
)
from paperscout.analysis.pdf_extract import (
    PdfExtractionError,
    PdfExtractionResult,
    PdfPageText,
    extract_pdf_pages,
)

__all__ = [
    "MaterialChunk",
    "MaterialDocument",
    "MaterialIssue",
    "MaterialSection",
    "PdfExtractionError",
    "PdfExtractionResult",
    "PdfPageText",
    "PreparedMaterials",
    "EvidenceSnippet",
    "ExplanationReport",
    "ExplanationSection",
    "LLMExplanationResult",
    "build_llm_explanation_messages",
    "build_material_chunks",
    "collect_evidence",
    "default_report_path",
    "extract_pdf_pages",
    "generate_explanation_report",
    "generate_llm_explanation_report",
    "load_prepared_materials",
    "prepare_materials",
    "render_evidence_digest",
    "split_text_into_sections",
    "suggested_questions",
    "suggested_reading_order",
    "write_explanation_report",
]
