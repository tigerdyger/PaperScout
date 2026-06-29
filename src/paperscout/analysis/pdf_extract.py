"""PDF text extraction helpers for PaperScout materials."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List


class PdfExtractionError(RuntimeError):
    """Raised when a PDF cannot be opened or parsed as text."""


@dataclass
class PdfPageText:
    page_number: int
    text: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class PdfExtractionResult:
    pages: List[PdfPageText]
    warnings: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "pages": [page.to_dict() for page in self.pages],
            "warnings": self.warnings,
        }


def extract_pdf_pages(path: Path) -> PdfExtractionResult:
    """Extract page text from a PDF using pypdf.

    This intentionally returns warnings instead of pretending PDF text
    extraction is complete. Equations, tables, figures, and layout frequently
    need separate handling in later stages.
    """

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is installed in CI
        raise PdfExtractionError(
            "pypdf is required for PDF text extraction; install PaperScout again"
        ) from exc

    path = Path(path)
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise PdfExtractionError(f"could not open PDF: {path}") from exc

    warnings = []
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise PdfExtractionError("encrypted PDF could not be decrypted") from exc

    pages = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            warnings.append(f"page {index} text extraction failed: {exc}")
            text = ""
        pages.append(PdfPageText(page_number=index, text=text.strip()))

    if not any(page.text for page in pages):
        warnings.append("no extractable text found in PDF")

    warnings.append(
        "PDF text extraction may lose equations, tables, figures, and layout"
    )
    return PdfExtractionResult(pages=pages, warnings=warnings)
