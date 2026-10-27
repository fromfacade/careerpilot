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


def test_word_per_line_education_becomes_one_structured_record():
    """The Google-Docs-PDF failure mode: every word on its own line,
    including a blank between tokens. Must become one education record,
    never one fact per word."""
    words = [
        "EDUCATION",
        "University",
        "of",
        "California,",
        "Santa",
        "Cruz",
        "—",
        "B.S.",
        "Computer",
        "Science,",
        "Expected",
        "Graduation",
        "December",
        "2027",
        "GPA:",
        "3.28/4.00",
    ]
    facts = parse_resume_text("\n\n".join(words))
    education = [f for f in facts if f.fact_type == FactType.EDUCATION]
    assert len(education) == 1
    record = education[0]
    assert "University of California" in record.fact_key
    assert "of" not in {f.fact_key.lower() for f in facts}
    assert record.fact_value["degree"] is not None
    assert "B.S" in record.fact_value["degree"]
    assert record.fact_value["major"] is not None
    assert "Computer Science" in record.fact_value["major"]
    assert record.fact_value["gpa"] == "3.28/4.00"
    assert record.fact_value["dates_text"] is not None
    assert "2027" in record.fact_value["dates_text"]
    # No extracted fact is a single leftover function-word.
    assert all(f.fact_key.lower() not in {"university", "of", "california,", "santa", "cruz"} for f in facts)


def test_multiline_education_stays_one_record():
    text = """EDUCATION
University of Example
B.S. Computer Science
Expected Graduation December 2027
GPA: 3.8/4.0
Relevant Coursework: Data Structures, Algorithms
"""
    facts = parse_resume_text(text)
    education = [f for f in facts if f.fact_type == FactType.EDUCATION]
    assert len(education) == 1
    value = education[0].fact_value
    assert value["institution"] is not None and "University of Example" in value["institution"]
    assert value["degree"] is not None
    assert value["major"] is not None and "Computer Science" in value["major"]
    assert value["gpa"] == "3.8/4.0"
    assert value["dates_text"] is not None
    assert value["coursework"] is not None and "Data Structures" in value["coursework"]


def test_work_experience_groups_employer_title_dates_and_bullets():
    text = """EXPERIENCE
Acme Corp
Backend Engineering Intern
Jun 2024 - Aug 2024
- Built a REST API serving 10k requests/day using Python and FastAPI
- Reduced query latency by 30% by adding database indexes
"""
    facts = parse_resume_text(text)
    jobs = [f for f in facts if f.fact_type == FactType.WORK_EXPERIENCE]
    assert len(jobs) == 1
    value = jobs[0].fact_value
    assert value["employer"] == "Acme Corp"
    assert value["position"] == "Backend Engineering Intern"
    assert value["dates_text"] is not None and "2024" in value["dates_text"]
    assert len(value["bullets"]) == 2


def test_project_groups_name_technologies_and_bullets():
    text = """PROJECTS
Personal Finance Tracker — React, Postgres, Docker
- Built a full-stack app to track expenses
- Deployed to a small VPS with Docker Compose
"""
    facts = parse_resume_text(text)
    projects = [f for f in facts if f.fact_type == FactType.PROJECT]
    assert len(projects) == 1
    value = projects[0].fact_value
    assert value["name"] == "Personal Finance Tracker"
    assert "React" in value["technologies"]
    assert "Postgres" in value["technologies"]
    assert len(value["bullets"]) == 2


def test_comma_separated_skills_stay_grouped_not_word_split():
    text = "SKILLS\nLanguages: Python, TypeScript, Go\nTools: Docker Compose, Git\n"
    facts = parse_resume_text(text)
    skills = [f for f in facts if f.fact_type == FactType.SKILL]
    by_key = {f.fact_key: f.fact_value["items"] for f in skills}
    assert by_key["Languages"] == ["Python", "TypeScript", "Go"]
    assert by_key["Tools"] == ["Docker Compose", "Git"]
    # Never one fact per comma-separated token as its own record key.
    assert "Python" not in {f.fact_key for f in skills}


def test_ordinary_prose_is_not_split_into_individual_facts():
    text = """EDUCATION
University of Example is a public research university in Example City.
"""
    facts = parse_resume_text(text)
    assert len(facts) == 1
    assert facts[0].fact_type == FactType.EDUCATION
    assert "is" not in {f.fact_key.lower() for f in facts}


def test_wrapped_sentence_tail_stays_in_the_same_record():
    text = """PROJECTS
Example Tracker
- Built a tool that recognizes common design
patterns.
EXPERIENCE
Acme Corp
Intern
Jun 2024 - Aug 2024
- Improved unit test
coverage.
"""
    facts = parse_resume_text(text)
    keys = {f.fact_key for f in facts}
    assert "patterns." not in keys
    assert "coverage." not in keys
    projects = [f for f in facts if f.fact_type == FactType.PROJECT]
    jobs = [f for f in facts if f.fact_type == FactType.WORK_EXPERIENCE]
    assert len(projects) == 1
    assert len(jobs) == 1
    assert any("patterns." in b for b in projects[0].fact_value["bullets"]) or "patterns." in projects[0].raw_text
    assert any("coverage." in b for b in jobs[0].fact_value["bullets"]) or "coverage." in jobs[0].raw_text


_FOUR_PROJECTS_RESUME = """Jane Doe
PROJECTS
TaskFlow - Backend Job Processing & Authentication Platform
Python, FastAPI, PostgreSQL, SQLAlchemy, Docker, JWT, REST APIs
- Built a Python/FastAPI backend service with PostgreSQL persistence for asynchronous job creation, status tracking, authentication, and
background processing.
- Developed secure password hashing, JWT-based access, email verification, and background workflows using production-oriented backend
patterns.
GlucoRelay - AI-Powered Safety Assistant
Python, FastAPI, Pydantic, Gemini API, Gemma, REST APIs
- Built a FastAPI backend for multilingual voice check-ins, converting natural-language responses into structured user states and backend actions.
- Integrated Google Gemma through the Gemini API to extract structured information while keeping safety-critical transitions controlled by
deterministic backend logic.
Spritz - Affordable Alternatives to Luxury Fragrances
Node.js, Express, Puppeteer, Gemini, PostgreSQL, Docker
- Built backend workflows in Node.js/Express using Puppeteer and Gemini to analyze fragrance profiles.
PC Build Visual Builder - Full-Stack PC Compatibility Tool
React, Next.js, TypeScript, Node.js, Express, PostgreSQL, Docker
- Developed a full-stack web application with a React/Next.js frontend and Node.js/Express backend.
"""

_TWO_JOBS_RESUME = """EXPERIENCE
LSS Tutoring Services - Santa Cruz, CA September 2024 - Present
Student Office Assistant
- Built and automated a utilization-tracking system used by staff to identify underused tutoring services and guide outreach and resource allocation
across multiple tutoring formats.
- Analyzed attendance, cancellation, and scheduling trends to surface underutilized sessions and support data-informed changes to tutoring
coverage.
Oakes HSG & Student Life - Santa Cruz, CA September 2024 - June
2025
Oakes Tech Crew Member
- Configured and operated A/V systems for events with 150+ attendees, troubleshooting hardware/software failures under strict time constraints.
- Documented technical best practices and contributed process improvements during weekly team syncs.
"""


def test_four_consecutive_projects_stay_separate_with_own_tech_and_bullets():
    facts = parse_resume_text(_FOUR_PROJECTS_RESUME)
    projects = [f for f in facts if f.fact_type == FactType.PROJECT]
    names = [f.fact_value["name"] for f in projects]
    assert names == ["TaskFlow", "GlucoRelay", "Spritz", "PC Build Visual Builder"]
    assert [f.fact_value["tagline"] for f in projects] == [
        "Backend Job Processing & Authentication Platform",
        "AI-Powered Safety Assistant",
        "Affordable Alternatives to Luxury Fragrances",
        "Full-Stack PC Compatibility Tool",
    ]
    taskflow, glucorelay, spritz, pc_build = projects
    assert "Gemini API" not in taskflow.fact_value["technologies"]
    assert "Gemma" not in taskflow.fact_value["technologies"]
    assert any("voice check-ins" in b for b in glucorelay.fact_value["bullets"])
    assert not any("voice check-ins" in b for b in taskflow.fact_value["bullets"])
    assert any("background processing." in b for b in taskflow.fact_value["bullets"])
    assert any("deterministic backend logic." in b for b in glucorelay.fact_value["bullets"])
    assert "Puppeteer" in spritz.fact_value["technologies"]
    assert "React" in pc_build.fact_value["technologies"]
    assert "background processing." in taskflow.raw_text


def test_two_consecutive_jobs_keep_their_own_dates_and_bullets():
    facts = parse_resume_text(_TWO_JOBS_RESUME)
    jobs = [f for f in facts if f.fact_type == FactType.WORK_EXPERIENCE]
    assert len(jobs) == 2
    first, second = jobs
    assert first.fact_value["employer"] == "LSS Tutoring Services"
    assert first.fact_value["position"] == "Student Office Assistant"
    assert first.fact_value["dates_text"] is not None and "Present" in first.fact_value["dates_text"]
    assert any("tutoring formats." in b for b in first.fact_value["bullets"])
    assert not any("A/V systems" in b for b in first.fact_value["bullets"])
    assert "across multiple tutoring formats." not in {first.fact_value["employer"], first.fact_key}
    assert second.fact_value["employer"] == "Oakes HSG & Student Life"
    assert second.fact_value["position"] == "Oakes Tech Crew Member"
    assert second.fact_value["dates_text"] is not None and "2025" in second.fact_value["dates_text"]
    assert any("A/V systems" in b for b in second.fact_value["bullets"])
    assert not any("tutoring formats." in b for b in second.fact_value["bullets"])


def test_wrapped_bullets_are_reconstructed_in_full():
    text = """PROJECTS
Example Tracker
- Built a tool that recognizes common design
patterns.
"""
    facts = parse_resume_text(text)
    project = [f for f in facts if f.fact_type == FactType.PROJECT][0]
    assert any("design patterns." in b for b in project.fact_value["bullets"])
    assert "design patterns." in project.raw_text


def test_glued_skill_string_is_split_into_individual_skills():
    text = "TECHNICAL SKILLS\nProgramming Languages: PythonJavaScriptTypeScriptSQLC++\n"
    facts = parse_resume_text(text)
    skills = [f for f in facts if f.fact_type == FactType.SKILL]
    assert len(skills) == 1
    assert skills[0].fact_value["items"] == ["Python", "JavaScript", "TypeScript", "SQL", "C++"]


def test_fastapi_is_not_split_by_camelcase():
    text = "SKILLS\nFrameworks: FastAPI, React\n"
    facts = parse_resume_text(text)
    skills = [f for f in facts if f.fact_type == FactType.SKILL]
    assert skills[0].fact_value["items"] == ["FastAPI", "React"]


def test_skill_table_row_becomes_category_items():
    text = "SKILLS\nFrontend: React | Next.js | TypeScript\n"
    facts = parse_resume_text(text)
    skills = [f for f in facts if f.fact_type == FactType.SKILL]
    assert skills[0].fact_value["items"] == ["React", "Next.js", "TypeScript"]


def test_organization_and_activity_description_are_one_record():
    text = """ACTIVITIES
Society of Hispanic Professional Engineers (SHPE), UCSC Chapter
- Participated in professional development and peer mentorship initiatives supporting students in STEM.
"""
    facts = parse_resume_text(text)
    activities = [f for f in facts if f.fact_type == FactType.ACHIEVEMENT]
    assert len(activities) == 1
    assert "SHPE" in (activities[0].fact_value["organization"] or "")
    assert any("peer mentorship" in b for b in activities[0].fact_value["bullets"])
    assert activities[0].verification_status if hasattr(activities[0], "verification_status") else True
    assert "SHPE" in activities[0].raw_text
    assert "peer mentorship" in activities[0].raw_text


def test_ambiguous_work_heading_does_not_invent_employer_or_title():
    text = """EXPERIENCE
Something Unclear
Another Unclear Line
- Did some work
"""
    facts = parse_resume_text(text)
    jobs = [f for f in facts if f.fact_type == FactType.WORK_EXPERIENCE]
    assert len(jobs) == 1
    assert jobs[0].fact_value["employer"] is None
    assert jobs[0].fact_value["position"] is None
    assert jobs[0].fact_value["dates_text"] is None
    assert jobs[0].fact_value["needs_review"] is True
    assert jobs[0].raw_text.startswith("Something Unclear")
    assert jobs[0].fact_value["bullets"] == ["Did some work"]
