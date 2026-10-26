"""Format-specific text extraction. The only job of this module is "get the
plain text out of the file bytes" -- no section/fact logic lives here, so
it stays swappable if a format gains a better extraction library later.
"""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.exceptions import ResumeExtractionError
from app.models.enums import ResumeFileFormat


def extract_text(file_bytes: bytes, file_format: ResumeFileFormat) -> str:
    """Return the plain text content of a resume file.

    Raises `ResumeExtractionError` if the bytes can't be read as the given
    format (corrupt file, encrypted PDF, etc.) or if extraction succeeds
    but yields no usable text at all. Never returns fabricated content.
    """
    if file_format == ResumeFileFormat.PDF:
        return _extract_pdf_text(file_bytes)
    if file_format == ResumeFileFormat.DOCX:
        return _extract_docx_text(file_bytes)
    # Unreachable given the ResumeFileFormat enum, but fail loudly rather
    # than silently returning empty text if a new format is ever added
    # here without updating this function.
    raise ResumeExtractionError(f"No extractor implemented for format: {file_format}")


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            raise ResumeExtractionError("PDF is password-protected; cannot extract text.")
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise ResumeExtractionError(f"Could not read PDF: {exc}") from exc
    except ResumeExtractionError:
        raise
    except Exception as exc:  # pypdf can raise a variety of error types on malformed input
        raise ResumeExtractionError(f"Could not read PDF: {exc}") from exc

    text = "\n".join(pages_text).strip()
    if not text:
        raise ResumeExtractionError("PDF contained no extractable text (scanned image? empty file?).")
    return text


def _extract_docx_text(file_bytes: bytes) -> str:
    try:
        document = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in document.paragraphs]
        # Resumes sometimes lay out skills/experience in tables rather than
        # paragraphs -- walk table cells too so that content isn't silently
        # dropped just because of how the author formatted the document.
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    paragraphs.append(cell.text)
    except Exception as exc:  # python-docx raises plain Exception/KeyError/zipfile errors on bad input
        raise ResumeExtractionError(f"Could not read DOCX: {exc}") from exc

    text = "\n".join(p for p in paragraphs if p is not None).strip()
    if not text:
        raise ResumeExtractionError("DOCX contained no extractable text.")
    return text
