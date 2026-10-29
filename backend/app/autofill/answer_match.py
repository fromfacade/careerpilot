"""Match one Greenhouse question to approved answers.

Meaning comes from the question kind and the kind of prompt it is.
Shared words are not enough. A library answer is reused only when the
employer, role, technology, and time context still fit this application.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from typing import Protocol

from app.autofill.greenhouse import question_kind_for
from app.services.answer_service import question_fingerprint


class _Answer(Protocol):
    question: str
    answer_text: str
    approval_status: str
    source: str
    role: str
    is_preferred: bool

_ROLE_FAMILIES = (
    ("backend", ("backend", "back end", "back-end", "server-side", "server side")),
    ("frontend", ("frontend", "front end", "front-end")),
    ("fullstack", ("fullstack", "full stack", "full-stack")),
    ("mobile", ("ios", "android", "mobile engineer", "mobile developer")),
    ("data", ("data engineer", "data scientist", "machine learning")),
)
_TECHS = (
    ("javascript", r"\bjavascript\b"),
    ("typescript", r"\btypescript\b"),
    ("python", r"\bpython\b"),
    ("java", r"\bjava\b"),
    ("react", r"\breact\b"),
    ("golang", r"\bgolang\b"),
    ("rust", r"\brust\b"),
    ("kotlin", r"\bkotlin\b"),
    ("swift", r"\bswift\b"),
    ("ruby", r"\bruby\b"),
    ("scala", r"\bscala\b"),
    ("sql", r"\bsql\b"),
)
_NOT_EMPLOYERS = frozenset(
    {
        "role",
        "company",
        "position",
        "team",
        "internship",
        "opportunity",
        "here",
        "this",
        "summer",
        "fall",
        "winter",
        "spring",
        "backend",
        "frontend",
        "python",
        "java",
        "javascript",
        "typescript",
        "react",
    }
)


@dataclass(frozen=True)
class AnswerJudgment:
    answer: _Answer | None
    match_kind: str
    explanation: str
    auto: bool
    basis: str = ""


def judge_answers(
    label: str,
    question_kind: str,
    answers: list[_Answer],
    *,
    employer: str,
    role: str,
) -> AnswerJudgment:
    judgments = [
        _judge(label, question_kind, answer, employer=employer, role=role)
        for answer in answers
        if answer.approval_status == "approved" and answer.answer_text.strip()
    ]
    return _choose(judgments)


def _choose(judgments: list[AnswerJudgment]) -> AnswerJudgment:
    job = [item for item in judgments if item.answer is not None and item.answer.source == "job_specific"]
    library = [item for item in judgments if item.answer is not None and item.answer.source != "job_specific"]
    for group in (
        [item for item in job if item.basis == "exact"],
        [item for item in job if item.basis == "equivalent"],
    ):
        chosen = _one(group)
        if chosen is not None:
            return chosen
    exact_library = [item for item in library if item.basis == "exact" and item.auto]
    if len(exact_library) > 1:
        preferred = [item for item in exact_library if item.answer is not None and item.answer.is_preferred]
        if len(preferred) == 1:
            return preferred[0]
        return _conflict()
    if len(exact_library) == 1:
        return exact_library[0]
    equivalent_library = [item for item in library if item.basis == "equivalent" and item.auto]
    if len(equivalent_library) == 1:
        return equivalent_library[0]
    if len(equivalent_library) > 1:
        return _conflict()
    uncertain = [item for item in judgments if item.match_kind == "uncertain_match"]
    if len(uncertain) == 1:
        return uncertain[0]
    if len(uncertain) > 1:
        return _conflict()
    return AnswerJudgment(None, "no_match", "No approved answer matches this question.", False)


def _one(group: list[AnswerJudgment]) -> AnswerJudgment | None:
    if len(group) == 1:
        return group[0]
    if len(group) > 1:
        return _conflict()
    return None


def _conflict() -> AnswerJudgment:
    return AnswerJudgment(
        None,
        "uncertain_match",
        "Review required because more than one approved answer matches this question.",
        False,
    )


def _judge(label: str, question_kind: str, answer: _Answer, *, employer: str, role: str) -> AnswerJudgment:
    exact = question_fingerprint(label) == question_fingerprint(answer.question)
    live = _context(label, question_kind)
    stored_kind = question_kind_for(answer.question)
    stored = _context(f"{answer.question}\n{answer.answer_text}", stored_kind or question_kind)
    live_roles = _families(role) | _families(label)
    stored_roles = _families(answer.role) | _families(answer.question) | _families(answer.answer_text)
    basis = "none"
    if exact:
        basis = "exact"
    elif _equivalent(live, stored, label, answer.question):
        basis = "equivalent"
    elif _related(live, stored):
        basis = "uncertain"
    if basis == "none":
        return _result(answer, "no_match", "none", "", False)

    if live.technologies and stored.technologies and live.technologies.isdisjoint(stored.technologies):
        return _result(answer, "no_match", "none", "", False)
    if live_roles and stored_roles and live_roles.isdisjoint(stored_roles):
        if _families(answer.answer_text) and _families(answer.answer_text).isdisjoint(live_roles):
            return _result(answer, "no_match", "none", "", False)
        return _result(
            answer,
            "uncertain_match",
            basis,
            "Review required because this answer was written for a different role.",
            False,
        )
    if _employer_conflict(stored.employers, employer):
        return _result(
            answer,
            "uncertain_match",
            basis,
            "Review required because this answer references a different employer.",
            False,
        )
    if stored.employers and not live.employers and basis != "exact":
        return _result(
            answer,
            "uncertain_match",
            basis,
            "Review required because this answer is specific to an employer.",
            False,
        )
    if live.time_sensitive and answer.source != "job_specific":
        return _result(answer, "uncertain_match", basis, _stale_reason(live.intent), False)
    if basis == "uncertain" or (live.technologies != stored.technologies and (live.technologies or stored.technologies)):
        return _result(
            answer,
            "uncertain_match",
            "uncertain",
            "Review required because this question is related, but the meaning is not the same.",
            False,
        )
    kind = "exact_match" if basis == "exact" else "equivalent_match"
    if answer.source == "job_specific" and basis == "exact":
        explanation = "Approved answer reused because this application already has an approved answer for this question."
    else:
        explanation = _reuse_reason(kind, live)
    return _result(answer, kind, basis, explanation, True)


def _result(answer: _Answer, kind: str, basis: str, explanation: str, auto: bool) -> AnswerJudgment:
    return AnswerJudgment(answer, kind, explanation, auto, basis)


@dataclass(frozen=True)
class _Context:
    intent: str
    employers: frozenset[str]
    technologies: frozenset[str]
    time_sensitive: bool


def _context(text: str, kind: str) -> _Context:
    intent = _intent(text, kind)
    return _Context(
        intent=intent,
        employers=frozenset(_employers(text)),
        technologies=frozenset(_technologies(text)),
        time_sensitive=intent in {"availability", "graduation", "gpa"},
    )


def _intent(text: str, kind: str) -> str:
    normalized = _words(text)
    if kind == "start_date" or "when can you start" in normalized or normalized == "start date":
        return "availability"
    if kind == "graduation_date" or "graduation" in normalized:
        return "graduation"
    if kind == "gpa" or "gpa" in set(normalized.split()) or "grade point" in normalized:
        return "gpa"
    if kind == "relocation" or "relocat" in normalized:
        return "relocation"
    if kind == "current_employer":
        return "employer"
    if kind in {"school", "degree", "major"}:
        return "education"
    if kind in {"github", "portfolio"}:
        return "link"
    if "project" in normalized and "experience" not in normalized:
        return "project"
    if kind == "experience" or "experience" in normalized:
        return "experience"
    if normalized.startswith("why ") or "interested in this" in normalized or "want to work" in normalized or "interest in this" in normalized:
        return "interest"
    return "other"


_GENERIC = frozenset(
    "why interested interest want work this role position job internship describe your relevant professional experience tell us about please technical project proud with using have you are do what how can start available open willing relocate relocation the a an to for of in on and or my our me question".split()
)
_QUALIFIER_SYNONYMS = {"position": "role", "job": "role", "internship": "role"}


def _equivalent(live: _Context, stored: _Context, live_label: str, stored_question: str) -> bool:
    if live.intent != stored.intent or live.intent in {"other", "link", "education"}:
        return False
    if live.technologies != stored.technologies:
        return False
    if _families(live_label) != _families(stored_question) and (_families(live_label) or _families(stored_question)):
        return False
    if live.employers != stored.employers and (live.employers or stored.employers):
        return False
    return _qualifiers(live_label) == _qualifiers(stored_question)


def _qualifiers(text: str) -> set[str]:
    return {
        _QUALIFIER_SYNONYMS.get(token, token)
        for token in _words(text).split()
        if token not in _GENERIC and len(token) > 2
    }


def _related(live: _Context, stored: _Context) -> bool:
    return live.intent == stored.intent and live.intent != "other"


def _employer_conflict(names: frozenset[str], application_employer: str) -> bool:
    if not names:
        return False
    current = application_employer.strip()
    if not current:
        return True
    return any(not _same_name(name, current) for name in names)


def _same_name(found: str, current: str) -> bool:
    left = found.casefold().strip()
    right = current.casefold().strip()
    if not left or not right:
        return False
    if left == right:
        return True
    return bool(re.search(rf"\b{re.escape(left)}\b", right) or re.search(rf"\b{re.escape(right)}\b", left))


def _employers(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in (r"\b(?:at|join|joining)\s+([A-Z][A-Za-z0-9]+)", r"\bWhy\s+([A-Z][A-Za-z0-9]+)\b"):
        for match in re.finditer(pattern, text):
            name = match.group(1)
            if name.casefold() not in _NOT_EMPLOYERS:
                found.add(name.casefold())
    return found


def _families(text: str) -> set[str]:
    normalized = _words(text)
    found = set()
    for family, phrases in _ROLE_FAMILIES:
        if any(phrase in normalized for phrase in phrases):
            found.add(family)
    return found


def _technologies(text: str) -> set[str]:
    normalized = text.casefold()
    return {name for name, pattern in _TECHS if re.search(pattern, normalized)}


def _stale_reason(intent: str) -> str:
    if intent == "availability":
        return "Review required because the available start date may no longer be current."
    if intent == "graduation":
        return "Review required because this graduation date may no longer be current."
    return "Review required because this GPA may no longer be current."


def _reuse_reason(kind: str, live: _Context) -> str:
    if kind == "exact_match":
        return "Approved answer reused because this question matches an approved answer for the same question."
    topic = _topic(live)
    return f"Approved answer reused because this question is equivalent to a previously answered {topic} question."


def _topic(live: _Context) -> str:
    if live.technologies:
        return f"{next(iter(live.technologies)).title()} experience"
    labels = {
        "interest": "interest",
        "experience": "experience",
        "project": "project",
        "relocation": "relocation",
        "availability": "availability",
        "employer": "employer",
    }
    return labels.get(live.intent, "application")


def _words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.casefold()).split())
