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
    "build_material_chunks",
    "collect_evidence",
    "default_report_path",
    "extract_pdf_pages",
    "generate_explanation_report",
    "load_prepared_materials",
    "prepare_materials",
    "split_text_into_sections",
    "suggested_questions",
    "suggested_reading_order",
    "write_explanation_report",
]
