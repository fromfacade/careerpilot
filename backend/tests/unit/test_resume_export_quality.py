from pathlib import Path

from app.services.resume_export import export_docx, export_pdf
from app.services.resume_tailor import flatten_tailored_lines, tailor_resume, visible_rows
from docx import Document
from pypdf import PdfReader

from tests.resume_export_fixtures import (
    AI_ANALYSIS,
    BACKEND_ANALYSIS,
    FULLSTACK_ANALYSIS,
    Candidate,
    realistic_facts,
)


def _render_pages(pdf_path: Path, dest: Path) -> list[Path]:
    import pypdfium2 as pdfium

    dest.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    paths = []
    for index, page in enumerate(document, start=1):
        image = page.render(scale=2).to_pil()
        out = dest / f"page-{index}.png"
        image.save(out)
        paths.append(out)
    return paths


def _ink_ratio(image_path: Path) -> float:
    from PIL import Image

    image = Image.open(image_path).convert("L")
    pixels = list(image.getdata())
    ink = sum(1 for pixel in pixels if pixel < 245)
    return ink / max(len(pixels), 1)


def test_backend_and_fullstack_select_different_projects():
    facts = realistic_facts()
    original = [dict(fact.fact_value) for fact in facts]
    backend = tailor_resume(Candidate(), facts, BACKEND_ANALYSIS)
    fullstack = tailor_resume(Candidate(), facts, FULLSTACK_ANALYSIS)
    ai = tailor_resume(Candidate(), facts, AI_ANALYSIS)
    backend_names = {row["title"] for row in visible_rows(backend, "projects")}
    fullstack_names = {row["title"] for row in visible_rows(fullstack, "projects")}
    ai_names = {row["title"] for row in visible_rows(ai, "projects")}
    assert backend_names == {"TaskFlow", "GlucoRelay"}
    assert fullstack_names == {"PC Build Visual Builder", "Spritz"}
    assert "GlucoRelay" in ai_names and "Spritz" in ai_names
    assert 2 <= len(backend_names) <= 3
    assert all(row.get("selection_reason") for row in visible_rows(backend, "projects"))
    assert all(len((row["detail"].get("included_bullet_indexes") or [])) <= 3 for row in visible_rows(backend, "projects"))
    assert [fact.fact_value for fact in facts] == original


def test_skills_stay_grouped_and_job_relevant_first():
    tailored = tailor_resume(Candidate(), realistic_facts(), BACKEND_ANALYSIS)
    skills = visible_rows(tailored, "skills")
    titles = [row["title"] for row in skills]
    assert titles[:5] == [
        "Programming Languages",
        "Backend / APIs",
        "Frontend",
        "Databases / Infrastructure",
        "Tools / Platforms",
    ]
    flatten = "\n".join(flatten_tailored_lines(tailored))
    assert "Programming Languages: Python" in flatten
    assert "Backend / APIs:" in flatten
    assert "Languages: English, Spanish" in flatten
    backend_items = next(row["detail"]["items"] for row in skills if row["title"] == "Backend / APIs")
    assert backend_items[0] in {"FastAPI", "REST APIs"}


def test_manual_include_override_and_export_consistency(tmp_path: Path):
    tailored = tailor_resume(Candidate(), realistic_facts(), BACKEND_ANALYSIS)
    hidden = next(row for row in tailored["projects"] if row["title"] == "Spritz")
    assert hidden["included"] is False
    hidden["included"] = True
    hidden["selection_reason"] = "Manually included."
    tailored["presentation"]["page_budget"] = "manual"
    pdf_path = export_pdf(tailored, tmp_path / "manual.pdf")
    docx_path = export_docx(tailored, tmp_path / "manual.docx")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    docx_text = "\n".join(paragraph.text for paragraph in Document(docx_path).paragraphs)
    for text in (pdf_text, docx_text):
        assert "Spritz" in text
        assert "TaskFlow" in text
        assert "SHPE" in text
        assert text.count("Participated in professional development and peer mentorship initiatives supporting students in STEM.") == 1


def test_realistic_backend_export_is_one_page_and_renders(tmp_path: Path):
    tailored = tailor_resume(Candidate(), realistic_facts(), BACKEND_ANALYSIS)
    pdf_path = export_pdf(tailored, tmp_path / "backend.pdf")
    pages = [page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages]
    assert len(pages) == 1
    text = pages[0]
    assert "Alex Rivera" in text
    assert "TaskFlow" in text
    assert "GlucoRelay" in text
    assert "PC Build Visual Builder" not in text
    assert "Programming Languages:" in text
    assert "SHPE" in text
    assert text.count("SHPE") == 1
    assert "Dates:" not in text
    assert "? Built" not in text
    images = _render_pages(pdf_path, tmp_path / "backend-pages")
    assert len(images) == 1
    assert _ink_ratio(images[0]) > 0.04
    assert tailored["quality"]["ok"] is True
    assert tailored["quality"]["page_count"] == 1


def test_fullstack_export_is_one_page(tmp_path: Path):
    tailored = tailor_resume(Candidate(), realistic_facts(), FULLSTACK_ANALYSIS)
    pdf_path = export_pdf(tailored, tmp_path / "fullstack.pdf")
    pages = [page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages]
    assert len(pages) == 1
    text = pages[0]
    assert "PC Build Visual Builder" in text
    assert "Spritz" in text
    assert "TaskFlow" not in text
    images = _render_pages(pdf_path, tmp_path / "fullstack-pages")
    assert len(images) == 1
    assert _ink_ratio(images[0]) > 0.04
