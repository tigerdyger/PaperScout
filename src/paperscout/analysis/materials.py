"""Prepare paper and supplementary materials for later analysis."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit
from urllib.request import urlopen

from paperscout.analysis.pdf_extract import PdfExtractionError, extract_pdf_pages
from paperscout.storage.schemas import PaperMetadata

DEFAULT_MATERIALS_CACHE_DIR = Path("data/cache/materials")
DEFAULT_MAX_CHUNK_CHARS = 1800
DEFAULT_MIN_CHUNK_CHARS = 400
DEFAULT_DIRECT_CONTEXT_CHAR_LIMIT = 12000

SUPPORTED_TEXT_SUFFIXES = {".md", ".txt"}
UNSUPPORTED_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz"}

SECTION_HEADING_PATTERN = re.compile(
    r"^("
    r"abstract|introduction|background|related work|methods?|methodology|"
    r"experiments?|results?|discussion|conclusions?|limitations?|references|"
    r"supplementary information|supporting information|appendix|"
    r"\d+\.?\s+[A-Z][A-Za-z0-9 ,:/()_-]{2,80}"
    r")$",
    re.IGNORECASE,
)


@dataclass
class MaterialIssue:
    code: str
    message: str
    severity: str = "warning"
    material_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialIssue":
        return cls(
            code=str(data["code"]),
            message=str(data["message"]),
            severity=str(data.get("severity") or "warning"),
            material_id=data.get("material_id"),
        )


@dataclass
class MaterialSection:
    material_id: str
    name: str
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialSection":
        return cls(
            material_id=str(data["material_id"]),
            name=str(data["name"]),
            text=str(data.get("text") or ""),
        )


@dataclass
class MaterialDocument:
    material_id: str
    kind: str
    status: str
    file_type: str = "unknown"
    source_path: Optional[str] = None
    source_url: Optional[str] = None
    text_char_count: int = 0
    sections: List[MaterialSection] = field(default_factory=list)
    issues: List[MaterialIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material_id": self.material_id,
            "kind": self.kind,
            "status": self.status,
            "file_type": self.file_type,
            "source_path": self.source_path,
            "source_url": self.source_url,
            "text_char_count": self.text_char_count,
            "sections": [section.to_dict() for section in self.sections],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialDocument":
        return cls(
            material_id=str(data["material_id"]),
            kind=str(data["kind"]),
            status=str(data["status"]),
            file_type=str(data.get("file_type") or "unknown"),
            source_path=data.get("source_path"),
            source_url=data.get("source_url"),
            text_char_count=int(data.get("text_char_count") or 0),
            sections=[
                MaterialSection.from_dict(section)
                for section in data.get("sections") or []
            ],
            issues=[
                MaterialIssue.from_dict(issue)
                for issue in data.get("issues") or []
            ],
        )


@dataclass
class MaterialChunk:
    chunk_id: str
    material_id: str
    kind: str
    section_name: str
    text: str
    char_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialChunk":
        return cls(
            chunk_id=str(data["chunk_id"]),
            material_id=str(data["material_id"]),
            kind=str(data["kind"]),
            section_name=str(data["section_name"]),
            text=str(data.get("text") or ""),
            char_count=int(data.get("char_count") or 0),
        )


@dataclass
class PreparedMaterials:
    paper: PaperMetadata
    documents: List[MaterialDocument]
    chunks: List[MaterialChunk]
    cache_path: Optional[str] = None
    issues: List[MaterialIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper": self.paper.to_dict(),
            "documents": [document.to_dict() for document in self.documents],
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "cache_path": self.cache_path,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PreparedMaterials":
        return cls(
            paper=PaperMetadata.from_dict(data["paper"]),
            documents=[
                MaterialDocument.from_dict(document)
                for document in data.get("documents") or []
            ],
            chunks=[
                MaterialChunk.from_dict(chunk)
                for chunk in data.get("chunks") or []
            ],
            cache_path=data.get("cache_path"),
            issues=[
                MaterialIssue.from_dict(issue)
                for issue in data.get("issues") or []
            ],
        )


def prepare_materials(
    paper: PaperMetadata,
    *,
    paper_pdf: Optional[str] = None,
    supplementary: Optional[str] = None,
    cache_dir: Path = DEFAULT_MATERIALS_CACHE_DIR,
    refresh: bool = False,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    direct_context_char_limit: int = DEFAULT_DIRECT_CONTEXT_CHAR_LIMIT,
) -> PreparedMaterials:
    """Prepare paper and optional SI text into sections and chunks.

    Local files are parsed in place. Remote URLs are downloaded into the cache.
    Parsed output is cached as JSON so later analysis stages do not repeatedly
    parse the same material.
    """

    paper_locator = paper_pdf or paper.extra.get("local_pdf_path") or paper.pdf_url
    supplementary_locator = (
        supplementary or paper.local_si_path or paper.si_url
    )
    cache_dir = Path(cache_dir)
    cache_path = _parsed_cache_path(
        cache_dir,
        paper,
        paper_locator=paper_locator,
        supplementary_locator=supplementary_locator,
    )
    if cache_path.exists() and not refresh:
        return PreparedMaterials.from_dict(
            json.loads(cache_path.read_text(encoding="utf-8"))
        )

    documents = [
        _prepare_one_document(
            kind="paper",
            locator=paper_locator,
            raw_dir=cache_dir / "raw",
            refresh=refresh,
            direct_context_char_limit=direct_context_char_limit,
        ),
        _prepare_one_document(
            kind="supplementary",
            locator=supplementary_locator,
            raw_dir=cache_dir / "raw",
            refresh=refresh,
            direct_context_char_limit=direct_context_char_limit,
        ),
    ]
    chunks = []
    for document in documents:
        if document.status != "parsed":
            continue
        chunks.extend(
            build_material_chunks(
                document,
                min_chars=min_chunk_chars,
                max_chars=max_chunk_chars,
            )
        )

    issues = [issue for document in documents for issue in document.issues]
    if not chunks:
        issues.append(
            MaterialIssue(
                code="no_material_chunks",
                message="No parseable paper or supplementary text chunks were produced.",
                severity="error",
            )
        )

    prepared = PreparedMaterials(
        paper=paper,
        documents=documents,
        chunks=chunks,
        cache_path=str(cache_path),
        issues=issues,
    )
    _write_prepared_materials(cache_path, prepared)
    return prepared


def build_material_chunks(
    document: MaterialDocument,
    *,
    min_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    max_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> List[MaterialChunk]:
    chunks = []
    chunk_index = 0
    buffer_text = ""
    buffer_section = ""

    def flush() -> None:
        nonlocal buffer_text, buffer_section, chunk_index
        if not buffer_text.strip():
            return
        chunk_index += 1
        chunks.append(
            MaterialChunk(
                chunk_id=f"{document.material_id}_chunk_{chunk_index}",
                material_id=document.material_id,
                kind=document.kind,
                section_name=buffer_section or "Full Text",
                text=buffer_text.strip(),
                char_count=len(buffer_text.strip()),
            )
        )
        buffer_text = ""
        buffer_section = ""

    for section in document.sections:
        for part in _split_long_text(section.text, max_chars):
            if len(buffer_text) + len(part) > max_chars and buffer_text:
                flush()
            if not buffer_section:
                buffer_section = section.name
            elif buffer_section != section.name:
                flush()
                buffer_section = section.name
            buffer_text += part + "\n"
            if len(buffer_text) >= min_chars:
                flush()

    flush()
    return chunks


def split_text_into_sections(
    text: str,
    *,
    material_id: str,
    default_name: str = "Full Text",
) -> List[MaterialSection]:
    lines = [line.strip() for line in text.splitlines()]
    sections = []
    current_name = default_name
    current_lines = []

    def flush() -> None:
        nonlocal current_lines
        section_text = "\n".join(line for line in current_lines if line).strip()
        if section_text:
            sections.append(
                MaterialSection(
                    material_id=material_id,
                    name=current_name,
                    text=section_text,
                )
            )
        current_lines = []

    for line in lines:
        if _looks_like_section_heading(line):
            flush()
            current_name = line
            continue
        current_lines.append(line)
    flush()

    if not sections and text.strip():
        return [
            MaterialSection(
                material_id=material_id,
                name=default_name,
                text=text.strip(),
            )
        ]
    return sections


def _prepare_one_document(
    *,
    kind: str,
    locator: Optional[str],
    raw_dir: Path,
    refresh: bool,
    direct_context_char_limit: int,
) -> MaterialDocument:
    material_id = kind
    if not locator:
        return MaterialDocument(
            material_id=material_id,
            kind=kind,
            status="missing",
            issues=[
                MaterialIssue(
                    code=f"{kind}_missing",
                    material_id=material_id,
                    message=f"No {kind} material path or URL was provided.",
                )
            ],
        )

    local_path, source_url, resolve_issue = _resolve_locator(
        str(locator),
        raw_dir=raw_dir,
        refresh=refresh,
    )
    if resolve_issue is not None:
        resolve_issue.material_id = material_id
        return MaterialDocument(
            material_id=material_id,
            kind=kind,
            status="failed",
            source_url=source_url,
            issues=[resolve_issue],
        )

    assert local_path is not None
    file_type = _file_type(local_path)
    document = MaterialDocument(
        material_id=material_id,
        kind=kind,
        status="parsed",
        file_type=file_type,
        source_path=str(local_path),
        source_url=source_url,
    )

    if file_type == "pdf":
        _parse_pdf_document(document)
    elif local_path.suffix.lower() in SUPPORTED_TEXT_SUFFIXES:
        _parse_text_document(document)
    elif local_path.suffix.lower() in UNSUPPORTED_ARCHIVE_SUFFIXES:
        _mark_failed(
            document,
            "unsupported_archive",
            "Archive supplementary files are recorded but not parsed yet.",
        )
    else:
        _mark_failed(
            document,
            "unsupported_file_type",
            f"Unsupported material file type: {local_path.suffix or 'unknown'}",
        )

    if document.status == "parsed":
        _append_text_quality_issues(document, direct_context_char_limit)
    return document


def _parse_pdf_document(document: MaterialDocument) -> None:
    try:
        extraction = extract_pdf_pages(Path(document.source_path or ""))
    except PdfExtractionError as exc:
        _mark_failed(document, "pdf_extraction_failed", str(exc))
        return

    text = "\n\n".join(page.text for page in extraction.pages if page.text).strip()
    document.sections = split_text_into_sections(
        text,
        material_id=document.material_id,
        default_name="Full Text",
    )
    document.text_char_count = sum(len(section.text) for section in document.sections)
    for warning in extraction.warnings:
        document.issues.append(
            MaterialIssue(
                code="pdf_text_extraction_warning",
                material_id=document.material_id,
                message=warning,
            )
        )
    if not document.sections:
        _mark_failed(document, "empty_extracted_text", "No text sections were extracted.")


def _parse_text_document(document: MaterialDocument) -> None:
    path = Path(document.source_path or "")
    text = path.read_text(encoding="utf-8", errors="ignore")
    document.sections = split_text_into_sections(
        text,
        material_id=document.material_id,
        default_name="Supplementary Text"
        if document.kind == "supplementary"
        else "Full Text",
    )
    document.text_char_count = sum(len(section.text) for section in document.sections)
    if not document.sections:
        _mark_failed(document, "empty_text_file", "No text sections were extracted.")


def _append_text_quality_issues(
    document: MaterialDocument, direct_context_char_limit: int
) -> None:
    text = "\n".join(section.text for section in document.sections)
    if len(text.strip()) < 200:
        document.issues.append(
            MaterialIssue(
                code="low_text_volume",
                material_id=document.material_id,
                message="Extracted text is very short; analysis may be incomplete.",
            )
        )
    if _printable_ratio(text) < 0.85:
        document.issues.append(
            MaterialIssue(
                code="possible_garbled_text",
                material_id=document.material_id,
                message="Extracted text contains many non-printable characters.",
            )
        )
    if document.text_char_count > direct_context_char_limit:
        document.issues.append(
            MaterialIssue(
                code="long_material_chunked",
                material_id=document.material_id,
                message=(
                    "Material is too long for one prompt-sized context and was "
                    "split into chunks."
                ),
            )
        )


def _mark_failed(document: MaterialDocument, code: str, message: str) -> None:
    document.status = "failed"
    document.issues.append(
        MaterialIssue(
            code=code,
            message=message,
            severity="error",
            material_id=document.material_id,
        )
    )


def _resolve_locator(
    locator: str,
    *,
    raw_dir: Path,
    refresh: bool,
) -> Tuple[Optional[Path], Optional[str], Optional[MaterialIssue]]:
    if _is_url(locator):
        try:
            return _download_url(locator, raw_dir=raw_dir, refresh=refresh), locator, None
        except OSError as exc:
            return None, locator, MaterialIssue(
                code="download_failed",
                severity="error",
                message=f"Could not download material URL: {exc}",
            )

    path = Path(locator).expanduser()
    if not path.exists():
        return None, None, MaterialIssue(
            code="local_file_missing",
            severity="error",
            message=f"Local material file does not exist: {path}",
        )
    return path, None, None


def _download_url(url: str, *, raw_dir: Path, refresh: bool) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = _download_suffix(url)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    path = raw_dir / f"{digest}{suffix}"
    if path.exists() and not refresh:
        return path
    with urlopen(url, timeout=30) as response:
        path.write_bytes(response.read())
    return path


def _download_suffix(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.lower()
    if parsed.netloc.lower().endswith("arxiv.org") and "/pdf/" in path:
        return ".pdf"
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".pdf", ".txt", ".md", ".zip", ".tar", ".gz", ".tgz"}:
        return suffix
    return ".bin"


def _parsed_cache_path(
    cache_dir: Path,
    paper: PaperMetadata,
    *,
    paper_locator: Optional[str],
    supplementary_locator: Optional[str],
) -> Path:
    cache_dir = Path(cache_dir)
    descriptor = {
        "paper": paper.identifier_keys() or {f"title:{paper.title.lower()}"},
        "paper_locator": _locator_descriptor(paper_locator),
        "supplementary_locator": _locator_descriptor(supplementary_locator),
    }
    digest = hashlib.sha256(
        json.dumps(_jsonable_descriptor(descriptor), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return cache_dir / "parsed" / f"{digest}.json"


def _locator_descriptor(locator: Optional[str]) -> Dict[str, Any]:
    if not locator:
        return {"locator": None}
    if _is_url(locator):
        return {"locator": locator, "type": "url"}
    path = Path(locator).expanduser()
    descriptor: Dict[str, Any] = {"locator": str(path), "type": "local"}
    if path.exists():
        stat = path.stat()
        descriptor["size"] = stat.st_size
        descriptor["mtime_ns"] = stat.st_mtime_ns
    else:
        descriptor["exists"] = False
    return descriptor


def _write_prepared_materials(path: Path, prepared: PreparedMaterials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(prepared.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in SUPPORTED_TEXT_SUFFIXES:
        return "text"
    if suffix in UNSUPPORTED_ARCHIVE_SUFFIXES:
        return "archive"
    return suffix.lstrip(".") or "unknown"


def _looks_like_section_heading(line: str) -> bool:
    if not line or len(line) > 100:
        return False
    if len(line.split()) > 12:
        return False
    return bool(SECTION_HEADING_PATTERN.match(line.strip()))


def _find_text_split(text: str, max_chars: int) -> int:
    preferred_markers = ("\n\n", "\n", ". ", "; ", ": ", ", ", " ")
    min_split = max(1, max_chars // 2)
    best = -1
    marker_len = 0
    for marker in preferred_markers:
        index = text.rfind(marker, 0, max_chars)
        if index >= min_split and index > best:
            best = index
            marker_len = len(marker)
    if best >= 0:
        return best + marker_len
    return max_chars


def _split_long_text(text: str, max_chars: int) -> Iterable[str]:
    remaining = text.strip()
    while len(remaining) > max_chars:
        end = _find_text_split(remaining, max_chars)
        part = remaining[:end].strip()
        if part:
            yield part
        remaining = remaining[end:].strip()
    if remaining:
        yield remaining


def _printable_ratio(text: str) -> float:
    if not text:
        return 1.0
    printable = sum(1 for character in text if character.isprintable() or character.isspace())
    return printable / len(text)


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _jsonable_descriptor(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {key: _jsonable_descriptor(item) for key, item in value.items()}
    return value
