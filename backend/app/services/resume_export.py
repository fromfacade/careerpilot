"""ATS-friendly DOCX/PDF export of a tailored resume document."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos
from pypdf import PdfReader

from app.core.exceptions import ValidationError
from app.services.resume_tailor import (
    _SECTION_TITLES,
    ascii_safe,
    assess_resume_quality,
    flatten_tailored_lines,
    hide_lowest_priority_content,
    iter_resume_lines,
    structured_entry_lines,
)

_SECTION_HEADINGS = set(_SECTION_TITLES.values())
_BODY_PT = 10
_NAME_PT = 14
_SECTION_PT = 11


def _pdf_safe(text: str) -> str:
    return ascii_safe(text).encode("latin-1", "replace").decode("latin-1")


def export_docx(document: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)
    header = document.get("header") or {}
    name = ascii_safe(header.get("full_name") or "Candidate")
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(name)
    run.bold = True
    run.font.size = Pt(16)
    contact = flatten_tailored_lines(document)
    if len(contact) > 1 and contact[1] not in _SECTION_HEADINGS:
        line = doc.add_paragraph(contact[1])
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for section, heading in _SECTION_TITLES.items():
        rows = [row for row in (document.get(section) or []) if row.get("included") is not False]
        if not rows:
            continue
        rendered = [line for row in rows for line in structured_entry_lines(row, section)]
        if not rendered:
            continue
        doc.add_heading(heading, level=1)
        for row in rows:
            lines = structured_entry_lines(row, section)
            if not lines:
                continue
            if section == "skills":
                for line in lines:
                    doc.add_paragraph(line)
                continue
            if lines[0].startswith("- "):
                for line in lines:
                    doc.add_paragraph(line[2:], style="List Bullet")
                continue
            heading_line = doc.add_paragraph()
            run = heading_line.add_run(lines[0])
            run.bold = True
            for line in lines[1:]:
                if line.startswith("- "):
                    doc.add_paragraph(line[2:], style="List Bullet")
                else:
                    meta = doc.add_paragraph(line)
                    if meta.runs:
                        meta.runs[0].italic = True
    doc.save(destination)
    validate_export(destination, document, kind="docx")
    return destination


def _style_for(kind: str) -> tuple[str, int, float, float]:
    if kind == "name":
        return "B", _NAME_PT, 7.0, 0.0
    if kind == "contact":
        return "", _BODY_PT, 5.2, 0.0
    if kind == "section":
        return "B", _SECTION_PT, 5.4, 0.0
    if kind == "heading":
        return "B", _BODY_PT, 5.2, 0.0
    if kind == "bullet":
        return "", _BODY_PT, 5.0, 4.0
    return "", _BODY_PT, 5.0, 0.0


def _measure_line(pdf: FPDF, kind: str, text: str) -> float:
    safe = _pdf_safe(text)
    style, size, height, indent = _style_for(kind)
    pdf.set_font("Helvetica", style, size)
    extra = 4.0 if kind == "section" else 0.0
    return extra + float(
        pdf.multi_cell(
            pdf.epw - indent,
            height,
            text=safe,
            dry_run=True,
            output=MethodReturnValue.HEIGHT,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    )


def _write_pdf_line(pdf: FPDF, kind: str, text: str) -> None:
    safe = _pdf_safe(text)
    style, size, height, indent = _style_for(kind)
    pdf.set_font("Helvetica", style, size)
    align = "C" if kind in {"name", "contact"} else "L"
    if kind == "section":
        pdf.ln(2.6)
        pdf.cell(pdf.epw, height, safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(40, 40, 40)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(1.6)
        return
    if indent:
        pdf.set_x(pdf.l_margin + indent)
    pdf.multi_cell(
        pdf.epw - indent,
        height,
        text=safe,
        align=align,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )


def _entry_chunks(lines: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for kind, text in lines:
        if kind in {"name", "contact", "section"}:
            if current:
                chunks.append(current)
                current = []
            chunks.append([(kind, text)])
        elif kind == "heading":
            if current:
                chunks.append(current)
            current = [(kind, text)]
        else:
            current.append((kind, text))
    if current:
        chunks.append(current)
    return chunks


def _keep_units(chunk: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    if not chunk or chunk[0][0] != "heading":
        return [chunk]
    lead: list[tuple[str, str]] = []
    rest: list[list[tuple[str, str]]] = []
    saw_bullet = False
    for kind, text in chunk:
        if not saw_bullet:
            lead.append((kind, text))
            if kind == "bullet":
                saw_bullet = True
        else:
            rest.append([(kind, text)])
    return ([lead] if lead else []) + rest


def _fits(pdf: FPDF, height: float) -> bool:
    return pdf.get_y() + height <= pdf.page_break_trigger


def _render_pdf_document(document: dict) -> FPDF:
    lines = iter_resume_lines(document)
    if not lines:
        raise ValidationError("Resume export has no content to write.")
    pdf = FPDF(format="Letter")
    pdf.set_margins(17, 14, 17)
    pdf.set_auto_page_break(auto=False, margin=14)
    pdf.add_page()
    for chunk in _entry_chunks(lines):
        for unit in _keep_units(chunk):
            height = sum(_measure_line(pdf, kind, text) for kind, text in unit)
            if not _fits(pdf, height):
                pdf.add_page()
            for kind, text in unit:
                _write_pdf_line(pdf, kind, text)
    return pdf


def _pdf_page_stats(pdf: FPDF) -> tuple[int, list[str]]:
    buffer = BytesIO()
    pdf.output(buffer)
    reader = PdfReader(buffer)
    pages = [page.extract_text() or "" for page in reader.pages]
    return len(pages), pages


def _sparse_last_page(pages: list[str]) -> bool:
    if len(pages) < 2:
        return False
    last = pages[-1].strip()
    return len(last) < 80 or last.count("\n") < 3


def _apply_one_page_budget(document: dict) -> None:
    if (document.get("presentation") or {}).get("page_budget") == "manual":
        return
    for _ in range(6):
        pages, texts = _pdf_page_stats(_render_pdf_document(document))
        if pages <= 1:
            return
        if pages == 2 and not _sparse_last_page(texts):
            return
        if not hide_lowest_priority_content(document):
            return


def export_pdf(document: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _apply_one_page_budget(document)
    pdf = _render_pdf_document(document)
    pdf.output(destination)
    validate_export(destination, document, kind="pdf")
    return destination


def _page_texts(path: Path) -> list[str]:
    reader = PdfReader(str(path))
    return [page.extract_text() or "" for page in reader.pages]


def validate_export(path: Path, document: dict, *, kind: str) -> None:
    expected = flatten_tailored_lines(document)
    if not expected:
        raise ValidationError("Resume export is missing required content.")
    previous = document.get("quality") or {}
    page_count = previous.get("page_count")
    empty_pages = 0
    if kind == "pdf":
        pages = _page_texts(path)
        page_count = len(pages)
        extracted = "\n".join(pages)
        empty_pages = sum(1 for page in pages if len(page.strip()) < 8)
        if empty_pages:
            raise ValidationError(f"PDF export produced {empty_pages} nearly empty page(s).")
        if _sparse_last_page(pages):
            raise ValidationError("PDF export produced a mostly empty second page.")
        if pages and len(extracted.strip()) < 40:
            raise ValidationError("PDF export did not contain extractable resume text.")
    else:
        extracted = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    quality = assess_resume_quality(
        document,
        extracted=extracted,
        page_count=page_count,
        empty_pages=empty_pages,
    )
    document["quality"] = quality
    if not quality["ok"]:
        raise ValidationError("Resume export failed quality checks: " + "; ".join(quality["issues"]))
    lowered = extracted.casefold()
    probes = [ascii_safe(line).strip() for line in expected if len(line.strip()) >= 4]
    missing = [probe for probe in probes[:24] if probe.casefold() not in lowered and probe[:18].casefold() not in lowered]
    if probes and missing and len(missing) > max(2, len(probes[:24]) // 3):
        raise ValidationError("Exported resume is missing expected text: " + "; ".join(missing[:4]))
    if probes and probes[0].casefold() not in lowered:
        raise ValidationError(f"Exported resume is missing the candidate name ({probes[0]}).")
