"""Choose an already selected resume and match approved answers.

This module only reads. It does not generate a resume, rewrite an answer,
call an AI provider, or attach a file to a page. Saved drafts are shown
for review and are not eligible to fill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.autofill.greenhouse import FormDetection
from app.models.enums import SENSITIVE_ANSWER_CATEGORIES

if TYPE_CHECKING:
    from app.autofill.mapping import AutofillPlan
from app.services.answer_service import question_fingerprint

_SENSITIVE_CATEGORIES = {item.value for item in SENSITIVE_ANSWER_CATEGORIES}


@dataclass(frozen=True)
class ResumeFileView:
    resume_id: int
    display_name: str
    file_format: str
    approved: bool
    archived: bool
    storage_path: str
    original_filename: str = ""


@dataclass(frozen=True)
class TailoredFileView:
    status: str
    pdf_path: str | None = None
    docx_path: str | None = None


@dataclass(frozen=True)
class AnswerView:
    id: int
    question: str
    answer_text: str
    approval_status: str
    origin: str
    category: str
    is_sensitive: bool = False
    is_reusable: bool = True
    is_preferred: bool = False
    source: str = "library"
    role: str = ""
    fact_labels: tuple[str, ...] = ()
    missing_notes: tuple[str, ...] = ()


@dataclass
class Materials:
    preparation_id: int | None = None
    resume: ResumeFileView | None = None
    tailored: TailoredFileView | None = None
    job_answers: list[AnswerView] = field(default_factory=list)
    library_answers: list[AnswerView] = field(default_factory=list)
    writing_style_profile_id: int | None = None
    link_problem: str | None = None
    employer: str = ""
    role: str = ""
    draft_answers: list[AnswerView] = field(default_factory=list)


@dataclass
class ResumePlan:
    status: str
    kind: str
    preparation_id: int | None
    resume_id: int | None
    display_name: str
    file_format: str | None
    approved: bool
    readable: bool
    compatible: bool
    eligible_for_attach: bool
    review_required: bool
    reason: str
    field_id: str | None = None
    upload_name: str = ""


@dataclass
class AnswerProposal:
    field_id: str
    label: str
    required: bool | None
    match_kind: str
    proposed_text: str | None
    proposed_replacement: str | None
    existing_value: str | None
    source: str | None
    source_id: int | None
    approval_status: str | None
    origin: str | None
    eligible_for_fill: bool
    review_required: bool
    uncertainty: str | None
    explanation: str = ""
    supporting_facts: list[str] = field(default_factory=list)
    input_type: str = "textarea"
    name: str = ""
    element_id: str = ""


@dataclass
class AnswerPlan:
    writing_style_profile_id: int | None = None
    answers_rewritten: bool = False
    matched: list[AnswerProposal] = field(default_factory=list)
    missing: list[AnswerProposal] = field(default_factory=list)
    ambiguous: list[AnswerProposal] = field(default_factory=list)
    sensitive: list[AnswerProposal] = field(default_factory=list)
    preserved: list[AnswerProposal] = field(default_factory=list)


def empty_resume(reason: str) -> ResumePlan:
    return ResumePlan(
        status="unavailable",
        kind="none",
        preparation_id=None,
        resume_id=None,
        display_name="",
        file_format=None,
        approved=False,
        readable=False,
        compatible=False,
        eligible_for_attach=False,
        review_required=True,
        reason=reason,
        upload_name="",
    )


def apply_materials(plan: AutofillPlan, detection: FormDetection, materials: Materials | None) -> None:
    materials = materials or Materials()
    if not detection.supported:
        plan.resume = empty_resume("This URL is not a supported application.")
        plan.answers = AnswerPlan(answers_rewritten=False)
        return
    accept = _resume_accept(detection)
    has_upload = _has_resume_upload(detection)
    plan.resume = select_resume(materials, accept, has_upload, _resume_field_id(detection))
    plan.answers = match_answers(detection, materials)


def select_resume(materials: Materials, accept: str, has_upload: bool, field_id: str | None = None) -> ResumePlan:
    if materials.link_problem:
        plan = empty_resume(materials.link_problem)
        plan.preparation_id = materials.preparation_id
        plan.field_id = field_id
        return plan
    if materials.preparation_id is None:
        plan = empty_resume("No application preparation is linked to this form, so no resume was selected.")
        plan.field_id = field_id
        return plan
    tailored = materials.tailored
    if tailored is not None and tailored.status == "approved":
        chosen = _from_tailored(materials, accept, has_upload)
    else:
        chosen = _from_original(materials, accept, has_upload)
    chosen.field_id = field_id
    return chosen


def match_answers(detection: FormDetection, materials: Materials) -> AnswerPlan:
    plan = AnswerPlan(writing_style_profile_id=materials.writing_style_profile_id, answers_rewritten=False)
    questions = [item for item in detection.fields if item.semantic in {"custom_question", "sensitive"} or _consentish(item.label)]
    for item in questions:
        if item.semantic == "sensitive" or _consentish(item.label):
            plan.sensitive.append(
                AnswerProposal(
                    field_id=item.field_id,
                    label=_clip(item.label),
                    required=item.required,
                    match_kind="sensitive",
                    proposed_text=None,
                    proposed_replacement=None,
                    existing_value=item.current_value,
                    source=None,
                    source_id=None,
                    approval_status=None,
                    origin=None,
                    eligible_for_fill=False,
                    review_required=True,
                    uncertainty="This question stays manual. Sensitive questions are not copied from other answers.",
                )
            )
            continue
        proposal = _match_question(
            item.field_id,
            item.label,
            item.required,
            item.current_value,
            item.confidence,
            item.question_kind,
            materials,
        )
        proposal.input_type = item.input_type or "textarea"
        proposal.name = item.name
        proposal.element_id = item.element_id
        _fit_listed_choices(proposal, item.options)
        if proposal.existing_value:
            plan.preserved.append(proposal)
        elif proposal.match_kind in {"exact_match", "equivalent_match"} and proposal.eligible_for_fill:
            plan.matched.append(proposal)
        elif proposal.match_kind == "uncertain_match" or proposal.match_kind in {"exact_match", "equivalent_match"}:
            plan.ambiguous.append(proposal)
        else:
            plan.missing.append(proposal)
    _attach_saved_drafts(plan, materials)
    return plan


def _match_question(field_id, label, required, existing, confidence, question_kind: str, materials: Materials) -> AnswerProposal:
    from app.autofill.answer_match import judge_answers

    base = AnswerProposal(
        field_id=field_id,
        label=_clip(label),
        required=required,
        match_kind="no_match",
        proposed_text=None,
        proposed_replacement=None,
        existing_value=existing,
        source=None,
        source_id=None,
        approval_status=None,
        origin=None,
        eligible_for_fill=False,
        review_required=True,
        uncertainty="No approved answer matches this question.",
        explanation="No approved answer matches this question.",
    )
    usable_job = [item for item in materials.job_answers if _usable(item)]
    usable_library = [item for item in materials.library_answers if _usable(item) and item.is_reusable]
    judged = judge_answers(
        label,
        question_kind,
        [*usable_job, *usable_library],
        employer=materials.employer,
        role=materials.role,
    )
    if judged.answer is None:
        base.match_kind = judged.match_kind
        base.explanation = judged.explanation
        if required and judged.match_kind == "no_match":
            base.uncertainty = "A required question has no approved answer."
            base.explanation = base.uncertainty
        elif judged.match_kind != "no_match":
            base.uncertainty = judged.explanation
        return base
    chosen = judged.answer
    text = chosen.answer_text
    base.source = chosen.source
    base.source_id = chosen.id
    base.approval_status = chosen.approval_status
    base.origin = chosen.origin
    base.match_kind = judged.match_kind
    base.explanation = judged.explanation
    if existing:
        base.proposed_replacement = None if _same(existing, text) else text
        base.uncertainty = "The field already has a value. Replacing it requires approval."
        base.explanation = base.uncertainty
        return base
    base.proposed_text = text
    if not judged.auto or confidence != "high":
        base.match_kind = "uncertain_match"
        base.uncertainty = (
            judged.explanation
            if not judged.auto
            else "The question label is not reliable enough to fill automatically."
        )
        base.explanation = base.uncertainty
        return base
    base.uncertainty = None
    base.review_required = False
    base.eligible_for_fill = True
    return base


def _attach_saved_drafts(plan: AnswerPlan, materials: Materials) -> None:
    """Show a saved draft on a no_match question. Never mark it fillable."""
    saved: dict[str, AnswerView] = {}
    for item in materials.draft_answers:
        saved.setdefault(question_fingerprint(item.question), item)
    if not saved:
        return
    for proposal in plan.missing:
        if proposal.match_kind != "no_match":
            continue
        draft = saved.get(question_fingerprint(proposal.label))
        if draft is None:
            continue
        proposal.source = "job_specific"
        proposal.source_id = draft.id
        proposal.approval_status = draft.approval_status
        proposal.origin = draft.origin
        proposal.eligible_for_fill = False
        proposal.review_required = True
        proposal.supporting_facts = list(draft.fact_labels)
        proposal.proposed_text = draft.answer_text.strip() or None
        if draft.approval_status == "rejected":
            proposal.explanation = "You rejected this draft. It will not be filled."
            proposal.uncertainty = proposal.explanation
            continue
        if draft.missing_notes:
            proposal.uncertainty = draft.missing_notes[0]
        else:
            proposal.uncertainty = "This draft is not filled until you approve it."
        facts = ", ".join(draft.fact_labels) if draft.fact_labels else "none on file"
        proposal.explanation = f"Draft only. Supported by verified facts: {facts}."


def _fit_listed_choices(proposal: AnswerProposal, options: list[str]) -> None:
    """An approved answer can fill a choice control only when every value is listed."""
    if proposal.input_type not in {"select", "radio", "checkbox", "checkboxes", "multi_select"}:
        return
    if not proposal.eligible_for_fill:
        return
    text = (proposal.proposed_text or proposal.proposed_replacement or "").strip()
    if not text or not options:
        proposal.eligible_for_fill = False
        proposal.review_required = True
        proposal.uncertainty = "This control's choices are not visible, so nothing was selected."
        proposal.explanation = proposal.uncertainty
        return
    parts = _choice_parts(text, options)
    chosen: list[str] = []
    for part in parts:
        match = _exact_listed(part, options)
        if match is None:
            proposal.eligible_for_fill = False
            proposal.review_required = True
            proposal.uncertainty = "No listed choice exactly matches the approved answer."
            proposal.explanation = proposal.uncertainty
            return
        if match not in chosen:
            chosen.append(match)
    fitted = "\n".join(chosen)
    if proposal.proposed_replacement:
        proposal.proposed_replacement = fitted
    else:
        proposal.proposed_text = fitted


def _choice_parts(text: str, options: list[str]) -> list[str]:
    exact = _exact_listed(text, options)
    if exact is not None:
        return [exact]
    parts = [part.strip() for part in re.split(r"\s*[,;\n]\s*", text) if part.strip()]
    return parts or [text]


def _exact_listed(value: str, options: list[str]) -> str | None:
    matches = [option for option in options if option.strip() and option.strip().casefold() == value.strip().casefold()]
    return matches[0] if len(matches) == 1 else None


def _usable(answer: AnswerView) -> bool:
    if answer.approval_status != "approved" or answer.is_sensitive:
        return False
    if answer.category in _SENSITIVE_CATEGORIES:
        return False
    return bool(answer.answer_text.strip())


def _from_original(materials: Materials, accept: str, has_upload: bool) -> ResumePlan:
    resume = materials.resume
    if resume is None:
        plan = empty_resume("No resume is selected on this preparation.")
        plan.preparation_id = materials.preparation_id
        return plan
    readable = _readable(resume.storage_path)
    compatible = readable and _compatible(resume.file_format, accept)
    approved = resume.approved and not resume.archived
    eligible = approved and readable and compatible and has_upload
    if not approved:
        reason = "The selected resume is not an approved active profile. Another resume was not substituted."
    elif not readable:
        reason = "The selected resume file is missing or unreadable."
    elif not _compatible(resume.file_format, accept):
        reason = f"This form does not accept a {resume.file_format.upper()} resume."
    elif not has_upload:
        reason = "The selected resume is approved, and this form has no resume upload."
    else:
        reason = "The approved original resume selected for this preparation will be used."
    return ResumePlan(
        status="ready" if eligible else "needs_review",
        kind="original" if approved else "none",
        preparation_id=materials.preparation_id,
        resume_id=resume.resume_id if approved else None,
        display_name=_safe_name(resume.display_name) if approved else "",
        file_format=resume.file_format if approved and readable else None,
        approved=approved,
        readable=readable,
        compatible=compatible,
        eligible_for_attach=eligible,
        review_required=not eligible,
        reason=reason,
        upload_name=_upload_name(resume.original_filename or resume.display_name, resume.file_format) if approved else "",
    )


def _from_tailored(materials: Materials, accept: str, has_upload: bool) -> ResumePlan:
    tailored = materials.tailored
    assert tailored is not None
    for fmt, path in (("pdf", tailored.pdf_path), ("docx", tailored.docx_path)):
        if path and _readable(path) and _compatible(fmt, accept) and has_upload:
            source_name = materials.resume.original_filename or materials.resume.display_name if materials.resume else ""
            return ResumePlan(
                status="ready",
                kind="tailored",
                preparation_id=materials.preparation_id,
                resume_id=materials.resume.resume_id if materials.resume else None,
                display_name=f"Tailored resume ({fmt.upper()})",
                file_format=fmt,
                approved=True,
                readable=True,
                compatible=True,
                eligible_for_attach=True,
                review_required=False,
                reason="The tailored resume was explicitly approved for this preparation.",
                upload_name=_upload_name(source_name, fmt, tailored=True),
            )
    readable = any(path and _readable(path) for path in (tailored.pdf_path, tailored.docx_path))
    return ResumePlan(
        status="needs_review",
        kind="tailored",
        preparation_id=materials.preparation_id,
        resume_id=materials.resume.resume_id if materials.resume else None,
        display_name="Tailored resume",
        file_format=None,
        approved=True,
        readable=readable,
        compatible=False,
        eligible_for_attach=False,
        review_required=True,
        reason="The approved tailored resume cannot be attached. The original file was not substituted.",
    )


def _resume_field_id(detection: FormDetection) -> str | None:
    for item in detection.fields:
        if item.semantic == "resume" and item.input_type == "file":
            return item.field_id
    return None


def _resume_accept(detection: FormDetection) -> str:
    for item in detection.fields:
        if item.semantic == "resume" and item.input_type == "file":
            return item.accept or ""
    return ""


def _has_resume_upload(detection: FormDetection) -> bool:
    return any(item.semantic == "resume" and item.input_type == "file" for item in detection.fields)


def _compatible(fmt: str, accept: str) -> bool:
    kind = fmt.casefold()
    if kind not in {"pdf", "docx"}:
        return False
    tokens = [part.strip().casefold() for part in (accept or "").split(",") if part.strip()]
    if not tokens:
        return True
    if kind == "pdf":
        return any(token in {".pdf", "pdf", "application/pdf"} or token.endswith(".pdf") for token in tokens)
    return any("docx" in token or "wordprocessingml" in token for token in tokens)


def _readable(path: str | None) -> bool:
    if not path:
        return False
    file = Path(path)
    try:
        if not file.is_file():
            return False
        with file.open("rb") as handle:
            handle.read(1)
    except OSError:
        return False
    return True


def _consentish(label: str) -> bool:
    text = question_fingerprint(label)
    return any(phrase in text for phrase in ("i agree", "i certify", "i consent", "terms and conditions", "privacy policy"))


def _same(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def _upload_name(original: str, file_format: str, tailored: bool = False) -> str:
    """Browser-facing filename. The stored file path is never used as this name."""
    ext = file_format.casefold().strip(".")
    if ext not in {"pdf", "docx"}:
        ext = "pdf"
    cleaned = Path(original or "").name
    cleaned = re.sub(r"[^A-Za-z0-9._() -]", "", cleaned).strip(" .")
    stem = Path(cleaned).stem if cleaned else ""
    stem = stem.strip(" .") or "Resume"
    if tailored:
        stem = f"{stem} tailored"
    return f"{stem}.{ext}"[:180]


def _safe_name(name: str) -> str:
    cleaned = Path(name).name.strip()
    return cleaned[:200]


def _clip(label: str) -> str:
    return label if len(label) <= 300 else label[:300]
