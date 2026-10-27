from pathlib import Path

from app.models.enums import FactType
from app.services.resume_export import export_docx, export_pdf
from app.services.resume_tailor import flatten_tailored_lines, structured_entry_lines, tailor_resume
from pypdf import PdfReader
from docx import Document


class _Fact:
    def __init__(self, id, fact_type, fact_key, fact_value):
        self.id = id
        self.fact_type = fact_type
        self.fact_key = fact_key
        self.fact_value = fact_value


class _Candidate:
    full_name = "Jane Doe"
    email = "jane@example.com"
    phone = None
    current_location = "California"
    school = "UCSC"
    linkedin_url = None
    github_url = None


def test_tailor_reorders_relevant_projects_and_does_not_invent():
    facts = [
        _Fact(1, FactType.PROJECT, "Campus Site", {"name": "Campus Site", "technologies": ["HTML"]}),
        _Fact(2, FactType.PROJECT, "Alpha Queue", {"name": "Alpha Queue", "technologies": ["FastAPI", "Redis"]}),
        _Fact(3, FactType.SKILL, "Languages", {"items": ["Python"]}),
    ]
    analysis = {
        "summary": "Backend engineer using FastAPI",
        "technologies": [{"text": "fastapi", "evidence": "stated"}],
        "required": [{"text": "Python", "evidence": "stated"}],
    }
    tailored = tailor_resume(_Candidate(), facts, analysis)
    assert [row["title"] for row in tailored["projects"]][0] == "Alpha Queue"
    blob = str(tailored)
    assert "NASA" not in blob
    assert "Alpha Queue" in blob
    assert tailored["source_fact_ids"] == [1, 2, 3]


def test_export_preserves_text_order(tmp_path: Path):
    document = {
        "header": {"full_name": "Jane Doe", "email": "jane@example.com"},
        "education": [{"title": "UCSC", "detail": {"school": "UCSC"}}],
        "projects": [{"title": "Alpha Queue", "detail": {"name": "Alpha Queue", "bullets": ["Queued jobs."]}}],
        "work_experience": [],
        "skills": [],
        "achievements": [],
    }
    docx_path = export_docx(document, tmp_path / "t.docx")
    pdf_path = export_pdf(document, tmp_path / "t.pdf")
    docx_text = "\n".join(p.text for p in Document(docx_path).paragraphs)
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    for text in (docx_text, pdf_text):
        assert text.index("Jane Doe") < text.index("Education") < text.index("UCSC")
        assert text.index("Projects") < text.index("Alpha Queue")
    assert flatten_tailored_lines(document)[0] == "Jane Doe"
    for text in (docx_text, pdf_text, "\n".join(flatten_tailored_lines(document))):
        assert "{" not in text
        assert "Queued jobs." in text
        assert "'name':" not in text


def test_structured_entry_renders_work_and_project_fields():
    work = structured_entry_lines(
        {
            "title": "Northwind",
            "detail": {
                "employer": "Northwind Tutoring",
                "position": "Office Assistant",
                "dates_text": "2024 – Present",
                "bullets": ["Built a tracker.", "Documented workflows."],
                "review_reasons": ["ignore this"],
            },
        },
        "work_experience",
    )
    assert work[0] == "Office Assistant — Northwind Tutoring"
    assert "Dates: 2024 – Present" in work
    assert "• Built a tracker." in work
    assert "review_reasons" not in " ".join(work)
    assert "{" not in "".join(work)

    project = structured_entry_lines(
        {
            "title": "Alpha Queue",
            "detail": {"name": "Alpha Queue", "technologies": ["FastAPI", "Redis"], "bullets": ["Queued jobs."]},
        },
        "projects",
    )
    assert project[0] == "Alpha Queue"
    assert "Technologies: FastAPI, Redis" in project
    assert "• Queued jobs." in project


def test_pdf_export_keeps_extractable_text_on_long_resume(tmp_path: Path):
    bullets = [f"Delivered feature number {index} for the campus platform." for index in range(1, 40)]
    document = {
        "header": {"full_name": "Alex Rivera", "email": "alex.rivera@example.com", "location": "Santa Cruz, CA"},
        "education": [{"title": "UCSC", "detail": {"institution": "UC Santa Cruz", "degree": "B.S. Computer Science"}}],
        "work_experience": [
            {
                "title": "Intern",
                "detail": {"employer": "Northwind Labs", "position": "Software Intern", "bullets": bullets[:12]},
            }
        ],
        "projects": [
            {
                "title": "TaskFlow",
                "detail": {"name": "TaskFlow", "technologies": ["FastAPI", "PostgreSQL"], "bullets": bullets[12:24]},
            }
        ],
        "skills": [{"title": "Languages", "detail": {"items": ["Python", "TypeScript"]}}],
        "achievements": [],
    }
    pdf_path = export_pdf(document, tmp_path / "long.pdf")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    assert "Alex Rivera" in pdf_text
    assert "Education" in pdf_text
    assert "TaskFlow" in pdf_text
    assert "Delivered feature number 1" in pdf_text
    assert "Delivered feature number 24" in pdf_text
    assert "{" not in pdf_text
    pages = PdfReader(str(pdf_path)).pages
    assert all((page.extract_text() or "").strip() for page in pages)
