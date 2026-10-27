"""ATS-friendly DOCX/PDF export of a tailored resume document."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from pypdf import PdfReader

from app.core.exceptions import ValidationError
from app.services.resume_tailor import (
    _SECTION_TITLES,
    ascii_safe,
    assess_resume_quality,
    flatten_tailored_lines,
    iter_resume_lines,
    structured_entry_lines,
)

_SECTION_HEADINGS = set(_SECTION_TITLES.values())


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
                doc.add_paragraph(lines[0] if lines else "")
                continue
            heading_line = doc.add_paragraph()
            run = heading_line.add_run(lines[0])
            run.bold = True
            for line in lines[1:]:
                if line.startswith("- "):
                    doc.add_paragraph(line[2:], style="List Bullet")
                else:
                    meta = doc.add_paragraph(line)
                    meta.runs[0].italic = True if meta.runs else False
    doc.save(destination)
    validate_export(destination, document, kind="docx")
    return destination


def _write_pdf_line(pdf: FPDF, kind: str, text: str) -> None:
    safe = _pdf_safe(text)
    if kind == "name":
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(pdf.epw, 7, text=safe, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return
    if kind == "contact":
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 4.8, text=safe, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return
    if kind == "section":
        pdf.ln(2.4)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 5, safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(40, 40, 40)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(1.6)
        return
    if kind == "heading":
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(pdf.epw, 4.8, text=safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return
    if kind == "bullet":
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(pdf.l_margin + 4)
        pdf.multi_cell(pdf.epw - 4, 4.3, text=safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 4.3, text=safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def export_pdf(document: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = iter_resume_lines(document)
    if not lines:
        raise ValidationError("Resume export has no content to write.")
    pdf = FPDF(format="Letter")
    pdf.set_margins(16, 12, 16)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    for kind, text in lines:
        _write_pdf_line(pdf, kind, text)
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
