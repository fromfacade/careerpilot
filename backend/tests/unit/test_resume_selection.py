from app.models.enums import FactType, ResumeCategory
from app.services.resume_selection import infer_job_focus, select_resume


class _Fact:
    def __init__(self, fact_key, fact_value):
        self.fact_key = fact_key
        self.fact_value = fact_value
        self.fact_type = FactType.PROJECT


class _Resume:
    def __init__(self, id, name, category, focus, *, approved=True, archived=False, primary=False):
        self.id = id
        self.profile_name = name
        self.profile_description = ""
        self.category = category
        self.focus_areas = focus
        self.is_approved = approved
        self.is_archived = archived
        self.is_primary = primary


BACKEND_JD = {
    "required": [{"text": "Experience with FastAPI and PostgreSQL"}],
    "preferred": [],
    "technologies": [{"text": "fastapi"}, {"text": "postgresql"}],
    "responsibilities": [{"text": "Build backend APIs"}],
}
FULLSTACK_JD = {
    "required": [{"text": "React and Next.js"}],
    "preferred": [{"text": "Node.js"}],
    "technologies": [{"text": "react"}, {"text": "node"}],
    "responsibilities": [{"text": "Build a visual frontend"}],
}
AI_JD = {
    "required": [{"text": "Experience with Gemini and applied ML"}],
    "preferred": [],
    "technologies": [{"text": "python"}],
    "responsibilities": [{"text": "Integrate GlucoRelay-style AI features"}],
}


def _profiles():
    return [
        _Resume(1, "General SWE Resume", ResumeCategory.GENERAL_SWE, ["python"], primary=True),
        _Resume(2, "Backend SWE Resume", ResumeCategory.BACKEND, ["FastAPI", "PostgreSQL", "TaskFlow"]),
        _Resume(3, "Full-Stack Resume", ResumeCategory.FULLSTACK, ["React", "Next.js", "PC Build Visual Builder"]),
        _Resume(4, "AI Resume", ResumeCategory.AI_ML, ["GlucoRelay", "Gemini"]),
        _Resume(5, "Old draft", ResumeCategory.CUSTOM, ["rust"], approved=False),
    ]


def test_infers_role_focus_from_posting():
    assert infer_job_focus(BACKEND_JD, "Backend Engineering Intern") is ResumeCategory.BACKEND
    assert infer_job_focus(FULLSTACK_JD, "Full-Stack Intern") is ResumeCategory.FULLSTACK
    assert infer_job_focus(AI_JD, "AI Engineering Intern") is ResumeCategory.AI_ML


def test_selects_backend_resume_and_explains():
    choice = select_resume(analysis=BACKEND_JD, title="Backend Intern", resumes=_profiles(), facts_by_resume={})
    assert choice.resume.id == 2
    assert choice.source.value == "automatic"
    assert "backend" in choice.reason.lower()
    assert "fastapi" in choice.reason.lower() or "postgresql" in choice.reason.lower()


def test_selects_fullstack_and_ai_profiles():
    fullstack = select_resume(analysis=FULLSTACK_JD, title="Full-Stack Intern", resumes=_profiles(), facts_by_resume={})
    assert fullstack.resume.id == 3
    ai = select_resume(analysis=AI_JD, title="AI Intern", resumes=_profiles(), facts_by_resume={})
    assert ai.resume.id == 4


def test_ignores_unapproved_and_falls_back_to_default():
    only_default = [
        _Resume(1, "General SWE Resume", ResumeCategory.GENERAL_SWE, ["python"], primary=True),
        _Resume(5, "Old draft", ResumeCategory.BACKEND, ["fastapi"], approved=False),
    ]
    choice = select_resume(analysis=BACKEND_JD, title="Backend Intern", resumes=only_default, facts_by_resume={})
    assert choice.resume.id == 1
    assert choice.source.value in {"fallback_default", "automatic"}


def test_no_approved_resumes_flags_review():
    choice = select_resume(
        analysis=BACKEND_JD,
        title="Backend Intern",
        resumes=[_Resume(5, "Old draft", ResumeCategory.BACKEND, ["fastapi"], approved=False)],
        facts_by_resume={},
    )
    assert choice.resume is None
    assert choice.source.value == "none"
    assert "approved" in choice.reason.lower()


def test_uses_resume_facts_without_inventing():
    resumes = [_Resume(9, "Project resume", ResumeCategory.CUSTOM, [], primary=True)]
    facts = {9: [_Fact("TaskFlow", {"technologies": ["FastAPI", "PostgreSQL"]})]}
    choice = select_resume(analysis=BACKEND_JD, title="Backend Intern", resumes=resumes, facts_by_resume=facts)
    assert choice.resume.id == 9
    assert "nasa" not in choice.reason.lower()
