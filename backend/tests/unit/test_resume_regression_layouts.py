"""Regression tests for the single-column resume layout that was mis-parsed.

Observed failure on a real text PDF: 4 work records instead of 2 (the
employer line and the `Location | Dates` line became separate records),
only 1 of 4 projects recognised (the other titles, tech lines, and bullets
fell into Skills), and 24 skill records instead of 6 categories.

Every test here goes through the real extractor on a real, generated PDF
or DOCX (see tests/resume_fixtures.py) -- not hand-written text -- so the
extraction, normalisation, section detection, segmentation, and
classification layers are all exercised together.
"""

from __future__ import annotations

from collections import Counter

import pytest
import resume_fixtures as rf
from resume_fixtures import Section, b, t, w

from app.models.enums import FactType, ResumeFileFormat
from app.resume_parsing.extractors import extract_text
from app.resume_parsing.section_parser import parse_resume_text

FORMATS = ["pdf", "docx"]


def _parse(sections: list[Section], fmt: str):
    if fmt == "pdf":
        data, file_format = rf.standard_pdf(sections), ResumeFileFormat.PDF
    else:
        data, file_format = rf.standard_docx(sections), ResumeFileFormat.DOCX
    return parse_resume_text(extract_text(data, file_format))


def _of(facts, fact_type: FactType):
    return [f for f in facts if f.fact_type == fact_type]


LAYOUTS = {
    "standard": rf.STANDARD_SECTIONS,
    "reordered": rf.reordered_sections(),
}


# ---- exact counts + correct attachment -----------------------------------
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_exact_record_counts(fmt, layout):
    facts = _parse(LAYOUTS[layout], fmt)
    counts = Counter(f.fact_type.value for f in facts)
    assert dict(counts) == rf.EXPECTED_COUNTS


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_work_records_keep_employer_position_location_dates_and_all_bullets(fmt, layout):
    jobs = _of(_parse(LAYOUTS[layout], fmt), FactType.WORK_EXPERIENCE)
    assert len(jobs) == 2
    first, second = (j.fact_value for j in jobs)

    assert first["employer"] == "Northwind Tutoring Services"
    assert first["position"] == "Student Office Assistant"
    assert first["location"] == "Springfield, ST"
    assert first["dates_text"] == "September 2024 – Present"
    assert len(first["bullets"]) == 3
    # The wrapped bullet is one bullet, not a bullet plus a stray fragment.
    assert any(
        x.startswith("Analyzed attendance") and x.endswith("support data-informed changes to tutoring coverage.")
        for x in first["bullets"]
    )

    assert second["employer"] == "Contoso Student Life"
    assert second["position"] == "Tech Crew Member"
    assert second["location"] == "Springfield, ST"
    assert second["dates_text"] == "September 2024 – June 2025"
    assert len(second["bullets"]) == 2
    assert not any("A/V systems" in x for x in first["bullets"])
    assert not any("tutoring" in x.lower() for x in second["bullets"])


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_location_or_date_is_ever_an_employer_or_a_record(fmt, layout):
    facts = _parse(LAYOUTS[layout], fmt)
    for job in _of(facts, FactType.WORK_EXPERIENCE):
        v = job.fact_value
        assert v["employer"] and "Springfield" not in v["employer"]
        assert v["position"] and "Springfield" not in v["position"]
        assert "2024" not in v["employer"] and "2024" not in v["position"]
        assert v["bullets"], "a work record must carry its bullets"
    for fact in facts:
        assert not fact.fact_key.startswith("Springfield")
        assert "September 2024" not in fact.fact_key


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_projects_keep_name_tagline_stack_and_own_bullets(fmt, layout):
    projects = _of(_parse(LAYOUTS[layout], fmt), FactType.PROJECT)
    assert [p.fact_value["name"] for p in projects] == rf.EXPECTED_PROJECT_NAMES
    assert [len(p.fact_value["bullets"]) for p in projects] == [4, 3, 3, 3]

    alpha, beta, gamma, delta = (p.fact_value for p in projects)
    assert alpha["tagline"] == "Backend Job Processing & Authentication Platform"
    assert alpha["technologies"] == ["Python", "FastAPI", "PostgreSQL", "SQLAlchemy", "Docker", "JWT", "REST APIs"]
    assert beta["technologies"] == ["Python", "FastAPI", "Pydantic", "Gemini API", "Gemma", "REST APIs"]
    assert gamma["technologies"] == ["Node.js", "Express", "Puppeteer", "Gemini", "PostgreSQL", "Docker"]
    assert delta["technologies"] == [
        "React", "Next.js", "TypeScript", "Node.js", "Express", "PostgreSQL", "Docker",
    ]  # fmt: skip

    # Bullets stay with their own project, including wrapped ones.
    assert any(x.endswith("and background processing.") for x in alpha["bullets"])
    assert any(x.endswith("transitions controlled by deterministic backend logic.") for x in beta["bullets"])
    assert not any("voice check-ins" in x for x in alpha["bullets"])
    assert not any("Puppeteer" in x for x in beta["bullets"])
    assert any("hackathon" in x for x in gamma["bullets"])
    # The Activities bullet must not leak into the last project.
    assert not any("mentorship" in x for x in delta["bullets"])


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_skills_are_exactly_the_six_categories_and_never_project_content(fmt, layout):
    skills = _of(_parse(LAYOUTS[layout], fmt), FactType.SKILL)
    assert [s.fact_key for s in skills] == rf.EXPECTED_SKILL_CATEGORIES

    by_category = {s.fact_key: s.fact_value["items"] for s in skills}
    # Comma-separated technologies are preserved one-to-one.
    assert by_category["Programming Languages"] == ["Python", "JavaScript", "TypeScript", "SQL", "C++"]
    assert by_category["Frontend"] == ["React", "Next.js"]
    assert by_category["Languages"] == ["English", "Spanish"]
    # Slash-joined names are single technologies, not split in half.
    assert "Linux/Unix" in by_category["Databases / Infrastructure"]
    assert "Git/GitHub" in by_category["Tools / Platforms"]

    all_items = [item for items in by_category.values() for item in items]
    project_text = " ".join(
        [p.raw_text for p in _of(_parse(LAYOUTS[layout], fmt), FactType.PROJECT)]
        + [" ".join(p.fact_value["bullets"]) for p in _of(_parse(LAYOUTS[layout], fmt), FactType.PROJECT)]
    )
    for item in all_items:
        assert len(item.split()) <= 4, f"sentence-like skill item: {item!r}"
        assert item not in {
            "Alpha Queue", "Beta Relay", "Gamma Scent", "Delta Builder", "Technologies",
        }  # fmt: skip
    for sentence in ("Built a", "Implemented", "Designed", "Developed", "Integrated", "Shipped"):
        assert not any(sentence in item for item in all_items)
    assert project_text  # sanity: the project text we compared against was non-empty


@pytest.mark.parametrize("fmt", FORMATS)
def test_education_and_achievement_records(fmt):
    facts = _parse(rf.STANDARD_SECTIONS, fmt)
    (education,) = _of(facts, FactType.EDUCATION)
    edu = education.fact_value
    assert edu["institution"] == "Example State University"
    assert edu["location"] == "Springfield, ST"
    assert edu["degree"] == "B.S."
    assert edu["major"] == "Computer Science"
    assert edu["gpa"] == "3.50/4.00"
    assert edu["dates_text"] == "Expected Graduation: December 2027"

    (achievement,) = _of(facts, FactType.ACHIEVEMENT)
    assert achievement.fact_key.startswith("Society of Example Engineers")
    assert len(achievement.fact_value["bullets"]) == 1
    assert "mentorship" in achievement.fact_value["bullets"][0]


@pytest.mark.parametrize("fmt", FORMATS)
def test_a_clean_resume_flags_nothing_for_review(fmt):
    """Review flags are for real ambiguity; a clean layout raises none."""
    for fact in _parse(rf.STANDARD_SECTIONS, fmt):
        assert not fact.fact_value.get("needs_review"), fact.fact_key


# ---- edge layouts ----------------------------------------------------------
@pytest.mark.parametrize("fmt", FORMATS)
def test_multiple_positions_at_one_employer_stay_separate_and_the_carry_is_flagged(fmt):
    section = Section(
        "EXPERIENCE",
        [
            t("Acme Robotics — Software Engineer"),
            t("Austin, TX | June 2024 – Present"),
            b("Built fleet telemetry dashboards for operations teams."),
            t("Software Engineering Intern"),
            t("Austin, TX | June 2023 – August 2023"),
            b("Wrote integration tests for the firmware update service."),
        ],
    )
    jobs = _of(_parse([section], fmt), FactType.WORK_EXPERIENCE)
    assert len(jobs) == 2
    first, second = (j.fact_value for j in jobs)
    assert (first["employer"], first["position"]) == ("Acme Robotics", "Software Engineer")
    assert (second["employer"], second["position"]) == ("Acme Robotics", "Software Engineering Intern")
    assert first["dates_text"] == "June 2024 – Present"
    assert second["dates_text"] == "June 2023 – August 2023"
    assert len(first["bullets"]) == 1 and len(second["bullets"]) == 1
    # The employer was inferred for the second record, so a human must confirm it.
    assert not first["needs_review"]
    assert second["needs_review"] and "employer" in second["ambiguous_fields"]


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    ("date_text", "expected"),
    [
        ("09/2022 – 05/2023", "09/2022 – 05/2023"),
        ("Sept 2021 - Present", "Sept 2021 - Present"),
        ("Summer 2020", "Summer 2020"),
        ("Jan. 2019 – Mar. 2020", "Jan. 2019 – Mar. 2020"),
        ("2017–2018", "2017–2018"),
        ("March 2022 – Present", "March 2022 – Present"),
    ],
)
def test_date_formats_are_kept_verbatim_and_never_split_a_record(fmt, date_text, expected):
    section = Section(
        "EXPERIENCE",
        [
            t("First Co — Analyst"),
            t(f"Remote | {date_text}"),
            b("Prepared quarterly reports for the finance team."),
            t("Second Inc — Developer"),
            t("Boston, MA | May 2015 – May 2016"),
            b("Shipped features for the billing platform."),
        ],
    )
    jobs = _of(_parse([section], fmt), FactType.WORK_EXPERIENCE)
    assert len(jobs) == 2
    assert jobs[0].fact_value["dates_text"] == expected
    assert jobs[0].fact_value["location"] == "Remote"
    assert jobs[0].fact_value["employer"] == "First Co"
    assert len(jobs[0].fact_value["bullets"]) == 1


@pytest.mark.parametrize("fmt", FORMATS)
def test_missing_optional_fields_stay_empty_and_are_never_invented(fmt):
    sections = [
        Section("EDUCATION", [t("Sample College — Portland, OR"), t("B.A. History | 2020 – 2024")]),
        Section(
            "EXPERIENCE",
            [t("Solo Studio — Freelance Designer"), t("2022 – Present"), b("Designed brand identities for shops.")],
        ),
        Section(
            "PROJECTS",
            [
                t("Mapper"),
                b("Created an interactive map of local trails."),
                t("Notes App — Offline-first notes"),
                b("Wrote sync logic for notes."),
            ],
        ),
    ]
    facts = _parse(sections, fmt)
    (education,) = _of(facts, FactType.EDUCATION)
    assert education.fact_value["gpa"] is None
    assert education.fact_value["degree"] == "B.A."

    (job,) = _of(facts, FactType.WORK_EXPERIENCE)
    assert job.fact_value["location"] is None
    assert job.fact_value["employer"] == "Solo Studio"
    assert job.fact_value["dates_text"] == "2022 – Present"

    mapper, notes = (p.fact_value for p in _of(facts, FactType.PROJECT))
    assert mapper["name"] == "Mapper" and mapper["tagline"] is None
    assert mapper["technologies"] == [] and len(mapper["bullets"]) == 1
    assert notes["name"] == "Notes App" and notes["tagline"] == "Offline-first notes"
    assert not _of(facts, FactType.SKILL), "no skills section means no skill facts"


@pytest.mark.parametrize("fmt", FORMATS)
def test_unclassifiable_header_is_flagged_not_guessed(fmt):
    section = Section(
        "EXPERIENCE",
        [
            t("Omega Works — Wizard"),
            t("Tulsa, OK | 2017–2018"),
            b("Filed records and handled the front desk."),
        ],
    )
    (job,) = _of(_parse([section], fmt), FactType.WORK_EXPERIENCE)
    v = job.fact_value
    assert v["location"] == "Tulsa, OK"
    assert v["dates_text"] == "2017–2018"
    assert v["employer"] is None and v["position"] is None
    assert v["needs_review"]
    assert {"employer", "position"} <= set(v["ambiguous_fields"])
    assert "Omega Works" in " ".join(v["unclassified_text"])
    assert len(v["bullets"]) == 1


@pytest.mark.parametrize("fmt", FORMATS)
def test_multiline_description_stays_one_bullet(fmt):
    section = Section(
        "PROJECTS",
        [
            t("Orbit — Scheduler"),
            t("Technologies: Go, Redis"),
            b("Designed a distributed scheduler that rebalances work across many workers while"),
            w("preserving ordering guarantees for each tenant and exposing metrics for"),
            w("capacity planning."),
            b("Wrote load tests that exercised failure recovery."),
        ],
    )
    (project,) = _of(_parse([section], fmt), FactType.PROJECT)
    bullets = project.fact_value["bullets"]
    assert len(bullets) == 2
    assert bullets[0].startswith("Designed a distributed scheduler")
    assert bullets[0].endswith("capacity planning.")
    assert project.fact_value["technologies"] == ["Go", "Redis"]


def test_blank_lines_between_records_are_optional():
    """PDF with blank separators and DOCX without parse to the same result."""
    pdf_facts = _parse(rf.STANDARD_SECTIONS, "pdf")
    docx_facts = _parse(rf.STANDARD_SECTIONS, "docx")

    def shape(facts):
        return [(f.fact_type.value, f.fact_key, len(f.fact_value.get("bullets", []))) for f in facts]

    assert shape(pdf_facts) == shape(docx_facts)


def test_all_extracted_facts_are_unverified_by_construction():
    """The parser output carries no verification status at all; the service
    layer is the only place a status is assigned, and it assigns UNVERIFIED."""
    for fact in _parse(rf.STANDARD_SECTIONS, "pdf"):
        assert not hasattr(fact, "verification_status")
        assert "verification_status" not in fact.fact_value


def test_sentence_inside_a_skills_section_is_flagged_never_a_skill():
    text = (
        "Jane Doe\nSKILLS\nProgramming Languages: Python, Go\n"
        "I have strong communication skills and enjoy collaborating with teams across the company.\n"
        "Frontend: React\n"
    )
    facts = parse_resume_text(text)
    skills = _of(facts, FactType.SKILL)
    assert [s.fact_key for s in skills] == ["Programming Languages", "Frontend"]
    assert all("communication" not in item for s in skills for item in s.fact_value["items"])
    (other,) = _of(facts, FactType.OTHER)
    assert other.fact_value["needs_review"] is True
