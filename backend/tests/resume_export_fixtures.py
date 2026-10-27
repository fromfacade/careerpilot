"""Realistic internship-resume facts for export-quality tests.

Names match the projects and activities used in the live candidate review
UI so selection behavior can be checked without reading production data.
Canonical facts are never written by these helpers.
"""

from __future__ import annotations

from app.models.enums import FactType


class Fact:
    def __init__(self, id, fact_type, fact_key, fact_value, identity_key=None):
        self.id = id
        self.fact_type = fact_type
        self.fact_key = fact_key
        self.fact_value = fact_value
        self.identity_key = identity_key or f"{fact_type.value}|{fact_key.casefold()}"


class Candidate:
    full_name = "Alex Rivera"
    email = "alex.rivera@example.com"
    phone = "(555) 010-0100"
    current_location = "Santa Cruz, CA"
    school = "UC Santa Cruz"
    linkedin_url = "linkedin.com/in/alexrivera"
    github_url = "github.com/alexrivera"
    portfolio_url = "alexrivera.dev"


def realistic_facts() -> list[Fact]:
    return [
        Fact(
            1,
            FactType.EDUCATION,
            "UC Santa Cruz",
            {
                "institution": "University of California, Santa Cruz",
                "degree": "B.S. Computer Science",
                "dates_text": "Expected Graduation: December 2027",
                "gpa": "3.50/4.00",
                "coursework": "Data Structures & Algorithms, Operating Systems, Databases",
            },
        ),
        Fact(
            2,
            FactType.WORK_EXPERIENCE,
            "LESS Tutoring",
            {
                "employer": "LESS Tutoring Services",
                "position": "Student Office Assistant",
                "location": "Santa Cruz, CA",
                "dates_text": "September 2024 - Present",
                "bullets": [
                    "Built and automated a utilization-tracking system used by staff to identify underused tutoring services.",
                    "Analyzed attendance, cancellation, and scheduling trends to support data-informed coverage changes.",
                    "Created reusable spreadsheet logic and workflow documentation to reduce manual tracking.",
                ],
            },
        ),
        Fact(
            3,
            FactType.WORK_EXPERIENCE,
            "Oakes HSG",
            {
                "employer": "Oakes HSG & Student Life",
                "position": "Tech Crew Member",
                "location": "Santa Cruz, CA",
                "dates_text": "September 2024 - June 2025",
                "bullets": [
                    "Configured and operated A/V systems for events with 150+ attendees.",
                    "Documented technical setup steps used by later crews.",
                ],
            },
        ),
        Fact(
            4,
            FactType.PROJECT,
            "TaskFlow",
            {
                "name": "TaskFlow",
                "tagline": "Backend job processing platform",
                "technologies": ["Python", "FastAPI", "PostgreSQL", "SQLAlchemy", "Docker", "JWT"],
                "bullets": [
                    "Built a FastAPI service with PostgreSQL persistence for asynchronous job creation and status tracking.",
                    "Implemented concurrency-safe job claiming so workers process queued tasks without duplicate execution.",
                    "Designed REST APIs and SQLAlchemy models with a clear split between database, service, and API layers.",
                    "Added password hashing, JWT access, and email verification workflows.",
                ],
            },
        ),
        Fact(
            5,
            FactType.PROJECT,
            "GlucoRelay",
            {
                "name": "GlucoRelay",
                "tagline": "AI-powered safety assistant",
                "technologies": ["Python", "FastAPI", "Pydantic", "Gemini API", "Gemma"],
                "bullets": [
                    "Built a FastAPI backend for multilingual voice check-ins that convert replies into structured states.",
                    "Integrated Gemma through the Gemini API while keeping safety-critical transitions deterministic.",
                    "Designed an idempotent state machine with timed rechecks and caregiver handoff endpoints.",
                ],
            },
        ),
        Fact(
            6,
            FactType.PROJECT,
            "Spritz",
            {
                "name": "Spritz",
                "tagline": "Fragrance matching platform",
                "technologies": ["Node.js", "Express", "Puppeteer", "Gemini", "PostgreSQL", "Docker"],
                "bullets": [
                    "Built backend workflows in Node.js/Express using Puppeteer and Gemini to analyze fragrance profiles.",
                    "Designed a Dockerized PostgreSQL schema to store fragrance notes and return ranked matches.",
                    "Shipped a working MVP in 36 hours with a four-person team during a hackathon.",
                ],
            },
        ),
        Fact(
            7,
            FactType.PROJECT,
            "PC Build Visual Builder",
            {
                "name": "PC Build Visual Builder",
                "tagline": "Full-stack compatibility tool",
                "technologies": ["React", "Next.js", "TypeScript", "Node.js", "Express", "PostgreSQL"],
                "bullets": [
                    "Developed a full-stack app with a React/Next.js frontend and a Node.js/Express backend.",
                    "Implemented constraint-driven component selection that filters CPUs, GPUs, and memory.",
                    "Designed a PostgreSQL schema for component specifications and containerized backend services.",
                ],
            },
        ),
        Fact(8, FactType.SKILL, "Programming Languages", {"items": ["Python", "JavaScript", "TypeScript", "SQL", "C++"]}),
        Fact(9, FactType.SKILL, "Backend / APIs", {"items": ["FastAPI", "Node.js", "Express", "REST APIs", "SQLAlchemy", "Pydantic", "JWT"]}),
        Fact(10, FactType.SKILL, "Frontend", {"items": ["React", "Next.js"]}),
        Fact(11, FactType.SKILL, "Databases / Infrastructure", {"items": ["PostgreSQL", "Docker", "Linux/Unix"]}),
        Fact(12, FactType.SKILL, "Tools / Platforms", {"items": ["Git/GitHub", "Vercel", "Google Gemini API"]}),
        Fact(13, FactType.SKILL, "Languages", {"items": ["English", "Spanish"]}),
        Fact(
            14,
            FactType.ACHIEVEMENT,
            "Society of Hispanic Professional Engineers",
            {
                "organization": "SHPE",
                "text": "Participated in professional development and peer mentorship initiatives supporting students in STEM.",
            },
        ),
    ]


BACKEND_ANALYSIS = {
    "summary": "Software engineering intern on backend services, APIs, and data stores.",
    "technologies": [{"text": "FastAPI"}, {"text": "Python"}, {"text": "PostgreSQL"}, {"text": "Docker"}],
    "required": [{"text": "REST APIs"}, {"text": "SQL"}],
    "responsibilities": [{"text": "Build backend services and background job processing."}],
}

FULLSTACK_ANALYSIS = {
    "summary": "Full-stack software engineering intern using React and Node.js.",
    "technologies": [{"text": "React"}, {"text": "Next.js"}, {"text": "TypeScript"}, {"text": "Node.js"}],
    "required": [{"text": "frontend"}, {"text": "PostgreSQL"}],
    "responsibilities": [{"text": "Build user interfaces and full-stack product features."}],
}

AI_ANALYSIS = {
    "summary": "AI engineering intern working with Gemini and applied LLM systems.",
    "technologies": [{"text": "Gemini API"}, {"text": "Python"}, {"text": "FastAPI"}],
    "required": [{"text": "machine learning"}, {"text": "Pydantic"}],
    "responsibilities": [{"text": "Integrate language models into reliable backend workflows."}],
}
