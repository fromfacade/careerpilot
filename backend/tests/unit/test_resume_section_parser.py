"""Unit tests for app.resume_parsing.section_parser.

All resume text used here is synthetic/fictitious (Jane Doe) -- never the
real candidate's actual resume content, matching the project's existing
PII hygiene in test fixtures.
"""

from __future__ import annotations

from app.models.enums import FactType
from app.resume_parsing.section_parser import parse_resume_text

_SAMPLE_RESUME = """Jane Doe
jane.doe@example.com | (555) 123-4567 | linkedin.com/in/janedoe

EDUCATION
University of Example - B.S. Computer Science
Sep 2021 - Jun 2025
GPA: 3.8/4.0

EXPERIENCE
Backend Engineering Intern, Acme Corp
Jun 2024 - Aug 2024
- Built a REST API serving 10k requests/day using Python and FastAPI
- Reduced query latency by 30% by adding database indexes

PROJECTS
Personal Finance Tracker
- Built a full-stack app with React and Postgres to track expenses
- Deployed to a small VPS with Docker Compose

SKILLS
Languages: Python, TypeScript, Go
Frameworks: FastAPI, React, Django

ACHIEVEMENTS
Dean's List, 4 semesters
Winner, University Hackathon 2023
"""


def test_parses_all_expected_section_types():
    facts = parse_resume_text(_SAMPLE_RESUME)
    fact_types = {f.fact_type for f in facts}
    assert fact_types == {
        FactType.EDUCATION,
        FactType.WORK_EXPERIENCE,
        FactType.PROJECT,
        FactType.SKILL,
        FactType.ACHIEVEMENT,
    }


def test_education_block_captures_institution_and_dates():
    facts = parse_resume_text(_SAMPLE_RESUME)
    education = [f for f in facts if f.fact_type == FactType.EDUCATION]
    assert len(education) == 1
    assert "University of Example" in education[0].fact_key
    assert education[0].fact_value["dates_text"] is not None
    assert "2021" in education[0].fact_value["dates_text"]
    # The verbatim source text must always be preserved for human review.
    assert "GPA: 3.8/4.0" in education[0].raw_text


def test_work_experience_captures_bullets_and_company():
    facts = parse_resume_text(_SAMPLE_RESUME)
    jobs = [f for f in facts if f.fact_type == FactType.WORK_EXPERIENCE]
    assert len(jobs) == 1
    assert "Acme Corp" in jobs[0].fact_key
    assert any("FastAPI" in b for b in jobs[0].fact_value["bullets"])
    assert any("30%" in b for b in jobs[0].fact_value["bullets"])


def test_project_block_captures_name_and_bullets():
    facts = parse_resume_text(_SAMPLE_RESUME)
    projects = [f for f in facts if f.fact_type == FactType.PROJECT]
    assert len(projects) == 1
    assert "Personal Finance Tracker" in projects[0].fact_key
    assert any("Docker Compose" in b for b in projects[0].fact_value["bullets"])


def test_skills_split_into_categorized_items():
    facts = parse_resume_text(_SAMPLE_RESUME)
    skills = [f for f in facts if f.fact_type == FactType.SKILL]
    by_key = {f.fact_key: f.fact_value["items"] for f in skills}
    assert by_key["Languages"] == ["Python", "TypeScript", "Go"]
    assert by_key["Frameworks"] == ["FastAPI", "React", "Django"]


def test_achievements_become_one_fact_per_line():
    facts = parse_resume_text(_SAMPLE_RESUME)
    achievements = [f for f in facts if f.fact_type == FactType.ACHIEVEMENT]
    texts = {f.fact_value["text"] for f in achievements}
    assert "Dean's List, 4 semesters" in texts
    assert "Winner, University Hackathon 2023" in texts


def test_no_recognizable_headers_falls_back_to_other_not_fabrication():
    text = "Jane Doe\nThis document has no resume-style section headers at all.\nJust prose."
    facts = parse_resume_text(text)
    assert len(facts) == 1
    assert facts[0].fact_type == FactType.OTHER
    # The raw text is preserved verbatim rather than silently dropped.
    assert "no resume-style section headers" in facts[0].raw_text


def test_empty_text_returns_no_facts():
    assert parse_resume_text("") == []
    assert parse_resume_text("   \n\n  ") == []


def test_never_fabricates_a_date_when_none_present():
    text = "EDUCATION\nUniversity of Example - B.S. Computer Science\n"
    facts = parse_resume_text(text)
    education = [f for f in facts if f.fact_type == FactType.EDUCATION]
    assert len(education) == 1
    assert education[0].fact_value["dates_text"] is None


def test_section_header_with_inline_content_after_colon():
    text = "SKILLS: Python, Go, Rust\n"
    facts = parse_resume_text(text)
    skills = [f for f in facts if f.fact_type == FactType.SKILL]
    assert len(skills) == 1
    assert skills[0].fact_value["items"] == ["Python", "Go", "Rust"]
