"""ATS-friendly DOCX/PDF export of a tailored resume document."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from pypdf import PdfReader

from app.core.exceptions import ValidationError
from app.services.resume_tailor import flatten_tailored_lines, structured_entry_lines


def export_docx(document: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    header = document.get("header") or {}
    name = header.get("full_name") or "Candidate"
    doc.add_heading(name, level=0)
    contact = " · ".join(part for part in (header.get("email"), header.get("phone"), header.get("location")) if part)
    if contact:
        doc.add_paragraph(contact)
    for section in ("education", "work_experience", "projects", "skills", "achievements"):
        rows = document.get(section) or []
        if not rows:
            continue
        doc.add_heading(section.replace("_", " ").title(), level=1)
        for row in rows:
            lines = structured_entry_lines(row, section)
            if not lines:
                continue
            heading = doc.add_paragraph()
            run = heading.add_run(lines[0])
            run.bold = True
            for line in lines[1:]:
                if line.startswith("• "):
                    doc.add_paragraph(line[2:], style="List Bullet")
                else:
                    doc.add_paragraph(line)
    doc.save(destination)
    validate_export(destination, document, kind="docx")
    return destination


def export_pdf(document: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in flatten_tailored_lines(document):
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            pdf.epw,
            6,
            text=line.encode("latin-1", "replace").decode("latin-1"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.output(destination)
    validate_export(destination, document, kind="pdf")
    return destination


def validate_export(path: Path, document: dict, *, kind: str) -> None:
    expected = flatten_tailored_lines(document)
    if kind == "pdf":
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        extracted = "\n".join(pages)
        empty_pages = sum(1 for page in pages if len(page.strip()) < 8)
        if empty_pages:
            raise ValidationError(f"PDF export produced {empty_pages} nearly empty page(s).")
        if reader.pages and len(extracted.strip()) < 40:
            raise ValidationError("PDF export did not contain extractable resume text.")
    else:
        extracted = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    lowered = extracted.casefold()
    if any(marker in extracted for marker in ("review_reasons", "'name':", '"ambiguous_fields"')):
        raise ValidationError("Exported resume contained parser metadata instead of formatted text.")
    probes = []
    for line in expected:
        probe = line.replace("• ", "").replace("—", "-").strip()
        if len(probe) >= 4:
            probes.append(probe)
    missing = [probe for probe in probes[:20] if probe.casefold() not in lowered and probe[:18].casefold() not in lowered]
    if probes and missing and len(missing) > max(2, len(probes[:20]) // 3):
        raise ValidationError("Exported resume is missing expected text: " + "; ".join(missing[:4]))
    if probes and probes[0].casefold() not in lowered:
        raise ValidationError(f"Exported resume is missing the candidate name ({probes[0]}).")
