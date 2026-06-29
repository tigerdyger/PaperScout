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
    "build_material_chunks",
    "extract_pdf_pages",
    "prepare_materials",
    "split_text_into_sections",
]
