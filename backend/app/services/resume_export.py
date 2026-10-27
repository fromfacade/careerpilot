"""ATS-friendly DOCX/PDF export of a tailored resume document."""

from __future__ import annotations

from contextvars import ContextVar
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
    _MAX_PROJECTS,
    _MIN_PROJECTS,
    _SECTION_TITLES,
    ascii_safe,
    assess_resume_quality,
    flatten_tailored_lines,
    iter_resume_lines,
    limit_entry_bullets,
    ranked_project_rows,
    set_coursework_visible,
    structured_entry_lines,
    _project_reason,
)

_SECTION_HEADINGS = set(_SECTION_TITLES.values())
_PAGE_FIT_MARGIN_MM = 2.0
_DEFAULT_PROFILE = {
    "body": 10,
    "name": 14,
    "section": 11,
    "spacing": "normal",
    "name_h": 6.4,
    "text_h": 4.8,
    "section_h": 5.0,
    "before": 2.2,
    "after": 1.2,
    "bullet_indent": 4.0,
}
_PROFILES = (
    _DEFAULT_PROFILE,
    {**_DEFAULT_PROFILE, "spacing": "compact", "name_h": 6.0, "text_h": 4.5, "section_h": 4.6, "before": 1.4, "after": 0.8},
    {
        "body": 9.5,
        "name": 13,
        "section": 10.5,
        "spacing": "compact",
        "name_h": 5.6,
        "text_h": 4.3,
        "section_h": 4.4,
        "before": 1.3,
        "after": 0.7,
        "bullet_indent": 3.5,
    },
    {
        "body": 9,
        "name": 12.5,
        "section": 10,
        "spacing": "compact",
        "name_h": 5.4,
        "text_h": 4.1,
        "section_h": 4.2,
        "before": 1.2,
        "after": 0.6,
        "bullet_indent": 3.5,
    },
)
_PROFILE: ContextVar[dict] = ContextVar("resume_pdf_profile", default=_DEFAULT_PROFILE)


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


def _metrics(kind: str) -> tuple[str, float, float, float, float, float]:
    profile = _PROFILE.get()
    body = float(profile["body"])
    if body < 9:
        body = 9
    if kind == "name":
        return "B", float(profile["name"]), float(profile["name_h"]), 0.0, 0.0, 0.0
    if kind == "contact":
        return "", body, float(profile["text_h"]), 0.0, 0.0, 0.3
    if kind == "section":
        return "B", float(profile["section"]), float(profile["section_h"]), 0.0, float(profile["before"]), float(profile["after"])
    if kind == "heading":
        return "B", body, float(profile["text_h"]), 0.0, 0.5, 0.0
    if kind == "bullet":
        return "", body, float(profile["text_h"]), float(profile["bullet_indent"]), 0.0, 0.0
    return "", body, float(profile["text_h"]), 0.0, 0.0, 0.0


def _measure_line(pdf: FPDF, kind: str, text: str) -> float:
    safe = _pdf_safe(text)
    style, size, height, indent, before, after = _metrics(kind)
    pdf.set_font("Helvetica", style, size)
    if kind == "section":
        wrapped = height
    else:
        wrapped = float(
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
    return before + wrapped + after


def _write_pdf_line(pdf: FPDF, kind: str, text: str) -> None:
    safe = _pdf_safe(text)
    style, size, height, indent, before, after = _metrics(kind)
    pdf.set_font("Helvetica", style, size)
    if before:
        pdf.ln(before)
    align = "C" if kind in {"name", "contact"} else "L"
    if kind == "section":
        pdf.cell(pdf.epw, height, safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(40, 40, 40)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    else:
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
    if after:
        pdf.ln(after)


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


def _is_manual_budget(document: dict) -> bool:
    return (document.get("presentation") or {}).get("page_budget") == "manual"


def _usable_page_height() -> float:
    pdf = FPDF(format="Letter")
    pdf.set_margins(17, 14, 17)
    pdf.set_auto_page_break(auto=False, margin=14)
    pdf.add_page()
    return pdf.page_break_trigger - pdf.t_margin


def _estimated_height(document: dict) -> float:
    pdf = FPDF(format="Letter")
    pdf.set_margins(17, 14, 17)
    pdf.set_auto_page_break(auto=False, margin=14)
    pdf.add_page()
    return sum(_measure_line(pdf, kind, text) for kind, text in iter_resume_lines(document))


def _one_page_with_skills(document: dict) -> bool:
    if _estimated_height(document) > _usable_page_height() - _PAGE_FIT_MARGIN_MM:
        return False
    pages, texts = _pdf_page_stats(_render_pdf_document(document))
    if pages != 1:
        return False
    first = texts[0] if texts else ""
    has_skills = any(row.get("included") is not False for row in (document.get("skills") or []))
    return (not has_skills) or "SKILLS" in first


def _set_included(row: dict, included: bool) -> None:
    row["included"] = included
    if not included:
        row["selection_reason"] = ""


def _explain_two_pages(document: dict, reason: str) -> None:
    presentation = document.setdefault("presentation", {})
    presentation["two_page_reason"] = reason


def _remember_profile(document: dict, profile: dict) -> None:
    presentation = document.setdefault("presentation", {})
    presentation["body_pt"] = profile["body"]
    presentation["spacing"] = profile["spacing"]
    presentation["typography"] = profile


def _fits_profile(document: dict, profile: dict) -> bool:
    token = _PROFILE.set(profile)
    try:
        return _one_page_with_skills(document)
    finally:
        _PROFILE.reset(token)


def _first_fitting_profile(document: dict) -> dict | None:
    for profile in _PROFILES:
        if _fits_profile(document, profile):
            _remember_profile(document, profile)
            return profile
    return None


def _doc_target(document: dict) -> set[str]:
    return set(document.get("emphasized_terms") or [])


def _project_title(row: dict) -> str:
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    return str(detail.get("name") or row.get("title") or "A project")


def _configure_layout(
    document: dict,
    projects: list[dict],
    *,
    work_limit: int,
    coursework: bool,
    achievement_rows: list[dict],
) -> None:
    chosen = {id(row) for row in projects}
    kept_achievements = {id(row) for row in achievement_rows}
    target = _doc_target(document)
    for row in document.get("projects") or []:
        _set_included(row, id(row) in chosen)
        if row.get("included") is not False:
            limit_entry_bullets(row, target, 2)
            if not row.get("selection_reason"):
                row["selection_reason"] = _project_reason(row)
    for row in document.get("work_experience") or []:
        if row.get("included") is False:
            continue
        limit_entry_bullets(row, target, work_limit)
    set_coursework_visible(document, coursework)
    for row in document.get("achievements") or []:
        row["included"] = id(row) in kept_achievements


def _apply_one_page_budget(document: dict) -> None:
    """Fit skills and up to three projects before shrinking below 10pt or dropping one."""
    presentation = document.setdefault("presentation", {})
    if _is_manual_budget(document):
        profile = _first_fitting_profile(document)
        if profile is None:
            _remember_profile(document, _DEFAULT_PROFILE)
            _explain_two_pages(
                document,
                "The entries you included need a second page at a readable size. Hide a project or bullet if you want a one-page internship resume.",
            )
        else:
            presentation.pop("two_page_reason", None)
        return

    ranked = ranked_project_rows(document)
    preferred = [row for row in ranked if row.get("included") is not False][:_MAX_PROJECTS]
    if not preferred:
        preferred = [row for row in ranked if (row.get("relevance") or 0) > 0][:_MAX_PROJECTS]
    optional_achievements = [row for row in (document.get("achievements") or []) if row.get("included") is not False]
    stages = [
        (preferred, 2, True, optional_achievements),
        (preferred, 1, True, optional_achievements),
        (preferred, 1, False, optional_achievements),
        (preferred, 1, False, []),
    ]
    for projects, work_limit, coursework, achievement_rows in stages:
        _configure_layout(
            document,
            projects,
            work_limit=work_limit,
            coursework=coursework,
            achievement_rows=achievement_rows,
        )
        if _first_fitting_profile(document) is not None:
            presentation.pop("two_page_reason", None)
            presentation.pop("tradeoff", None)
            return

    if len(preferred) > _MIN_PROJECTS:
        dropped = preferred[-1]
        kept = preferred[:-1]
        for work_limit, coursework, achievement_rows in ((2, True, optional_achievements), (2, True, []), (1, False, [])):
            _configure_layout(
                document,
                kept,
                work_limit=work_limit,
                coursework=coursework,
                achievement_rows=achievement_rows,
            )
            if _first_fitting_profile(document) is not None:
                presentation.pop("two_page_reason", None)
                presentation["tradeoff"] = (
                    f"{_project_title(dropped)} did not fit with the other projects at 9pt. "
                    "It was left off so this stays a readable one-page resume. "
                    "Include it if you would rather use a second page."
                )
                return

    _remember_profile(document, _DEFAULT_PROFILE)
    _explain_two_pages(
        document,
        "These sections still need a second page at 9pt. Hide a lower-priority entry if you want one page.",
    )


def export_pdf(document: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _apply_one_page_budget(document)
    profile = (document.get("presentation") or {}).get("typography") or _DEFAULT_PROFILE
    token = _PROFILE.set(profile)
    try:
        pdf = _render_pdf_document(document)
    finally:
        _PROFILE.reset(token)
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
        if _sparse_last_page(pages) and not _is_manual_budget(document):
            raise ValidationError("PDF export produced a mostly empty second page.")
        if (
            not _is_manual_budget(document)
            and page_count
            and page_count > 1
            and any(row.get("included") is not False for row in (document.get("skills") or []))
            and "SKILLS" not in pages[0]
        ):
            raise ValidationError("Skills were pushed off the first page of the internship resume.")
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
