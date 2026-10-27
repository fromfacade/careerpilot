"""Unit tests for PDF/DOCX extraction whitespace repair."""

from __future__ import annotations

from app.resume_parsing.text_normalize import fragmentation_score, normalize_extracted_text


def test_fragmentation_score_is_one_when_every_line_is_a_single_token():
    text = "University\n\nof\n\nCalifornia,\n\nSanta\n\nCruz\n"
    assert fragmentation_score(text) == 1.0


def test_rejoins_google_docs_style_one_word_per_line_stream():
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
    ]
    # Alternate a blank line between every word -- the observed pypdf
    # "plain" extract of a Google Docs resume.
    fragmented = "\n\n".join(words)
    repaired = normalize_extracted_text(fragmented)

    assert "University of California, Santa Cruz" in repaired
    assert "B.S. Computer Science" in repaired
    assert "Expected Graduation December 2027" in repaired
    assert repaired.splitlines()[0] == "EDUCATION"
    # Ordinary prose must not remain one token per line.
    nonempty = [line for line in repaired.splitlines() if line.strip()]
    assert all(len(line.split()) > 1 or line == "EDUCATION" for line in nonempty)


def test_preserves_already_well_formed_lines():
    text = "EDUCATION\nUniversity of Example - B.S. Computer Science\nSep 2021 - Jun 2025\n"
    assert normalize_extracted_text(text) == text.strip()


def test_collapses_layout_mode_column_padding():
    text = "University of Example          Santa Cruz, CA\nB.S. Computer Science"
    repaired = normalize_extracted_text(text)
    assert "          " not in repaired
    assert "University of Example Santa Cruz, CA" in repaired


def test_empty_input_stays_empty():
    assert normalize_extracted_text("") == ""
    assert normalize_extracted_text("   \n\n  ") == ""


def test_rejoins_wrapped_bullet_and_date_without_merging_next_heading():
    text = """
- Built a utilization-tracking system used by staff to identify underused tutoring services and guide outreach and resource allocation
across multiple tutoring formats.
Oakes HSG & Student Life - Santa Cruz, CA September 2024 - June
2025
- Configured and operated A/V systems
"""
    repaired = normalize_extracted_text(text)
    assert "allocation across multiple tutoring formats." in repaired
    assert "June 2025" in repaired
    assert "Oakes HSG & Student Life" in repaired
    lines = [line for line in repaired.splitlines() if line.strip()]
    oakes = next(line for line in lines if line.startswith("Oakes"))
    assert "2025" in oakes
    assert not oakes.lower().startswith("across")


def test_does_not_glue_the_next_project_title_onto_a_wrapped_bullet():
    text = """
- Developed secure password hashing, JWT-based access, email verification, and background workflows using production-oriented backend
patterns.
GlucoRelay - AI-Powered Safety Assistant
Python, FastAPI, Gemma
"""
    repaired = normalize_extracted_text(text)
    assert "backend patterns." in repaired
    assert "GlucoRelay - AI-Powered Safety Assistant" in repaired
    assert "patterns. GlucoRelay" not in repaired
