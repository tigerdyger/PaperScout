import json
from pathlib import Path

from paperscout.analysis import materials
from paperscout.analysis.materials import (
    MaterialDocument,
    build_material_chunks,
    prepare_materials,
    split_text_into_sections,
)
from paperscout.analysis.pdf_extract import PdfExtractionResult, PdfPageText
from paperscout.storage.schemas import PaperMetadata


def test_prepare_materials_reads_pdf_and_optional_si(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF fake")
    si_path = tmp_path / "si.txt"
    si_path.write_text(
        "Supporting Information\n"
        "Additional implementation details and hyperparameters.\n",
        encoding="utf-8",
    )

    def fake_extract_pdf_pages(path):
        assert path == pdf_path
        return PdfExtractionResult(
            pages=[
                PdfPageText(
                    page_number=1,
                    text=(
                        "Abstract\n"
                        "This paper studies molecular dynamics force fields.\n"
                        "Methods\n"
                        "The model uses an energy-conserving architecture."
                    ),
                )
            ],
            warnings=["layout warning"],
        )

    monkeypatch.setattr(materials, "extract_pdf_pages", fake_extract_pdf_pages)

    prepared = prepare_materials(
        PaperMetadata(title="Material paper", arxiv_id="2401.00001"),
        paper_pdf=str(pdf_path),
        supplementary=str(si_path),
        cache_dir=tmp_path / "cache",
    )

    assert prepared.cache_path
    assert len(prepared.documents) == 2
    assert prepared.documents[0].status == "parsed"
    assert prepared.documents[1].status == "parsed"
    assert [section.name for section in prepared.documents[0].sections] == [
        "Abstract",
        "Methods",
    ]
    assert any(chunk.kind == "paper" for chunk in prepared.chunks)
    assert any(chunk.kind == "supplementary" for chunk in prepared.chunks)
    assert any(issue.message == "layout warning" for issue in prepared.issues)
    assert prepared.cache_path is not None
    assert json.loads(Path(prepared.cache_path).read_text(encoding="utf-8"))


def test_prepare_materials_uses_cached_parse(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF fake")

    monkeypatch.setattr(
        materials,
        "extract_pdf_pages",
        lambda path: PdfExtractionResult(
            pages=[PdfPageText(page_number=1, text="Abstract\nCached text")],
            warnings=[],
        ),
    )
    first = prepare_materials(
        PaperMetadata(title="Cached paper", arxiv_id="2401.00002"),
        paper_pdf=str(pdf_path),
        cache_dir=tmp_path / "cache",
    )

    def fail_extract_pdf_pages(path):
        raise AssertionError("cached materials should not be parsed again")

    monkeypatch.setattr(materials, "extract_pdf_pages", fail_extract_pdf_pages)
    second = prepare_materials(
        PaperMetadata(title="Cached paper", arxiv_id="2401.00002"),
        paper_pdf=str(pdf_path),
        cache_dir=tmp_path / "cache",
    )

    assert second.cache_path == first.cache_path
    assert second.documents[0].sections[0].text == "Cached text"


def test_prepare_materials_records_missing_and_unsupported_si(tmp_path) -> None:
    si_path = tmp_path / "si.zip"
    si_path.write_bytes(b"fake zip")

    prepared = prepare_materials(
        PaperMetadata(title="Missing paper", arxiv_id="2401.00003"),
        paper_pdf=str(tmp_path / "missing.pdf"),
        supplementary=str(si_path),
        cache_dir=tmp_path / "cache",
    )

    statuses = {document.kind: document.status for document in prepared.documents}
    codes = {issue.code for issue in prepared.issues}

    assert statuses == {"paper": "failed", "supplementary": "failed"}
    assert "local_file_missing" in codes
    assert "unsupported_archive" in codes
    assert "no_material_chunks" in codes


def test_prepare_materials_treats_arxiv_pdf_url_as_pdf(tmp_path, monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"%PDF fake"

    def fake_urlopen(url, timeout):
        assert url == "https://arxiv.org/pdf/2401.00005v1"
        assert timeout == 30
        return FakeResponse()

    def fake_extract_pdf_pages(path):
        assert path.suffix == ".pdf"
        return PdfExtractionResult(
            pages=[PdfPageText(page_number=1, text="Abstract\nDownloaded text")],
            warnings=[],
        )

    monkeypatch.setattr(materials, "urlopen", fake_urlopen)
    monkeypatch.setattr(materials, "extract_pdf_pages", fake_extract_pdf_pages)

    prepared = prepare_materials(
        PaperMetadata(title="Downloaded arXiv", arxiv_id="2401.00005"),
        paper_pdf="https://arxiv.org/pdf/2401.00005v1",
        cache_dir=tmp_path / "cache",
    )

    assert prepared.documents[0].status == "parsed"
    assert prepared.documents[0].file_type == "pdf"


def test_split_text_into_sections_detects_common_headings() -> None:
    sections = split_text_into_sections(
        "Abstract\nShort summary.\nMethods\nDetailed method text.",
        material_id="paper",
    )

    assert [section.name for section in sections] == ["Abstract", "Methods"]


def test_build_material_chunks_splits_long_sections() -> None:
    document = MaterialDocument(
        material_id="paper",
        kind="paper",
        status="parsed",
        sections=[
            materials.MaterialSection(
                material_id="paper",
                name="Methods",
                text="alpha beta gamma delta epsilon " * 20,
            )
        ],
    )

    chunks = build_material_chunks(document, min_chars=20, max_chars=60)

    assert len(chunks) > 1
    assert all(chunk.kind == "paper" for chunk in chunks)
    assert all(chunk.section_name == "Methods" for chunk in chunks)


def test_prepare_materials_warns_when_text_is_too_long(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF fake")

    monkeypatch.setattr(
        materials,
        "extract_pdf_pages",
        lambda path: PdfExtractionResult(
            pages=[PdfPageText(page_number=1, text="Methods\n" + "long text " * 50)],
            warnings=[],
        ),
    )

    prepared = prepare_materials(
        PaperMetadata(title="Long paper", arxiv_id="2401.00004"),
        paper_pdf=str(pdf_path),
        cache_dir=tmp_path / "cache",
        direct_context_char_limit=100,
        max_chunk_chars=80,
    )

    assert "long_material_chunked" in {issue.code for issue in prepared.issues}
    assert len(prepared.chunks) > 1
