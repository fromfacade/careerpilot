"""Decide which reviewed fields may be filled. Does not touch a browser.

A fill is allowed only when the live plan still shows the same field, the
same meaning, and the same value the user reviewed. Submission is refused
here so later browser code has no submit action to perform.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.autofill.mapping import AutofillPlan


class SubmissionBlocked(RuntimeError):
    """CareerPilot has no submission action."""


def refuse_submission(action: str) -> None:
    if (action or "").strip().casefold() in {"submit", "click_submit", "request_submit"}:
        raise SubmissionBlocked("CareerPilot does not submit applications.")


@dataclass(frozen=True)
class ReviewedField:
    field_id: str
    semantic: str
    label: str
    input_type: str
    name: str
    element_id: str
    proposed: str
    required: bool | None
    kind: str
    existing: str | None = None


@dataclass(frozen=True)
class FillAction:
    field_id: str
    input_type: str
    name: str
    element_id: str
    label: str
    value: str
    kind: str


@dataclass
class FillDecision:
    actions: list[FillAction] = field(default_factory=list)
    resume_field_id: str | None = None
    preserved: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    stale_details: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    stop_reason: str | None = None


def reviewed_fields(plan: AutofillPlan) -> dict[str, ReviewedField]:
    found: dict[str, ReviewedField] = {}
    for item in plan.ready:
        if item.eligible_for_fill and item.proposed_value:
            found[item.field_id] = _from_plan_field(item, item.proposed_value, "contact")
    for item in plan.answers.matched:
        if item.eligible_for_fill and item.proposed_text:
            found[item.field_id] = ReviewedField(
                field_id=item.field_id,
                semantic="custom_question",
                label=item.label,
                input_type=item.input_type or "textarea",
                name=item.name or item.field_id,
                element_id=item.element_id or item.field_id,
                proposed=item.proposed_text,
                required=item.required,
                kind="answer",
            )
    for item in plan.preserve_existing:
        if item.proposed_replacement:
            found[item.field_id] = _from_plan_field(item, item.proposed_replacement, "preserve")
    for item in plan.answers.preserved:
        if item.proposed_replacement:
            found[item.field_id] = ReviewedField(
                field_id=item.field_id,
                semantic="custom_question",
                label=item.label,
                input_type=item.input_type or "textarea",
                name=item.name or item.field_id,
                element_id=item.element_id or item.field_id,
                proposed=item.proposed_replacement,
                required=item.required,
                kind="preserve",
            )
    return found


def decide_fill(
    reviewed: dict[str, ReviewedField],
    live: AutofillPlan,
    *,
    included: set[str],
    overwrite: set[str],
    attach_resume: bool,
) -> FillDecision:
    decision = FillDecision()
    if "captcha" in live.blockers or "mfa" in live.blockers:
        decision.stop_reason = "A CAPTCHA or verification step is on the page. CareerPilot stopped."
        return decision
    live_by_id = _live_index(live)
    for field_id in included:
        current = reviewed.get(field_id)
        if current is None or current.semantic in {"sensitive", "unknown"}:
            decision.stale.append(field_id)
            continue
        fresh = _same_control(current, live_by_id)
        if fresh is None:
            decision.stale.append(field_id)
            if _identity_count(current, live_by_id) > 1:
                decision.stale_details[field_id] = "More than one field asks this question, so it was left for review."
            continue
        if fresh.existing and _same(fresh.existing, current.proposed):
            decision.preserved.append(field_id)
            continue
        if fresh.existing and field_id not in overwrite:
            decision.preserved.append(field_id)
            continue
        if current.kind == "preserve" and field_id not in overwrite:
            decision.preserved.append(field_id)
            continue
        if not _same(fresh.proposed, current.proposed):
            decision.stale.append(field_id)
            continue
        decision.actions.append(
            FillAction(
                field_id=field_id,
                input_type=fresh.input_type,
                name=fresh.name,
                element_id=fresh.element_id,
                label=fresh.label,
                value=current.proposed,
                kind=current.kind,
            )
        )
    if attach_resume and live.resume.eligible_for_attach and live.resume.field_id:
        reviewed_resume = reviewed.get("__resume__")
        if reviewed_resume is None or reviewed_resume.proposed != f"{live.resume.kind}:{live.resume.resume_id}:{live.resume.file_format}":
            decision.stale.append(live.resume.field_id)
        else:
            decision.resume_field_id = live.resume.field_id
    return decision


def revealed_actions(original: dict[str, ReviewedField], live: AutofillPlan, *, done: set[str]) -> FillDecision:
    """Fill verified fields that were hidden until an earlier answer was selected."""
    fresh = reviewed_fields(live)
    known_ids = set(original)
    known = {_identity(item) for item in original.values()}
    included = {
        field_id
        for field_id, item in fresh.items()
        if item.kind == "contact"
        and item.semantic not in {"sensitive", "unknown"}
        and field_id not in done
        and field_id not in known_ids
        and _identity(item) not in known
    }
    return decide_fill(fresh, live, included=included, overwrite=set(), attach_resume=False)


def _same_control(current: ReviewedField, live_by_id: dict[str, ReviewedField]) -> ReviewedField | None:
    fresh = live_by_id.get(current.field_id)
    if fresh is not None and fresh.semantic == current.semantic and _norm(fresh.label) == _norm(current.label):
        return fresh
    matches = [item for item in live_by_id.values() if _identity(item) == _identity(current)]
    if len(matches) == 1:
        return matches[0]
    return None


def _identity_count(current: ReviewedField, live_by_id: dict[str, ReviewedField]) -> int:
    return sum(1 for item in live_by_id.values() if _identity(item) == _identity(current))


def _identity(item: ReviewedField) -> str:
    return f"{item.semantic}|{_norm(item.label)}"


def resume_marker(plan: AutofillPlan) -> ReviewedField | None:
    resume = plan.resume
    if not resume.eligible_for_attach or not resume.field_id:
        return None
    return ReviewedField(
        field_id="__resume__",
        semantic="resume",
        label=resume.display_name,
        input_type="file",
        name=resume.field_id,
        element_id="",
        proposed=f"{resume.kind}:{resume.resume_id}:{resume.file_format}",
        required=True,
        kind="resume",
    )


def _from_plan_field(item, proposed: str, kind: str) -> ReviewedField:
    return ReviewedField(
        field_id=item.field_id,
        semantic=item.semantic,
        label=item.label,
        input_type=item.input_type,
        name=item.name,
        element_id=item.element_id,
        proposed=proposed,
        required=item.required,
        kind=kind,
    )


def _live_index(plan: AutofillPlan) -> dict[str, ReviewedField]:
    indexed: dict[str, ReviewedField] = {}
    for item in list(plan.ready) + list(plan.clarification) + list(plan.missing_required) + list(plan.preserve_existing):
        _put_live(
            indexed,
            field_id=item.field_id,
            semantic=item.semantic,
            label=item.label,
            input_type=item.input_type,
            name=item.name,
            element_id=item.element_id,
            proposed=item.proposed_value or item.proposed_replacement or "",
            required=item.required,
            existing=item.existing_value,
        )
    for item in plan.answers.matched + plan.answers.missing + plan.answers.ambiguous + plan.answers.preserved:
        _put_live(
            indexed,
            field_id=item.field_id,
            semantic="custom_question",
            label=item.label,
            input_type=item.input_type or "textarea",
            name=item.name or item.field_id,
            element_id=item.element_id or item.field_id,
            proposed=item.proposed_text or item.proposed_replacement or "",
            required=item.required,
            existing=item.existing_value,
        )
    return indexed


def _put_live(indexed: dict[str, ReviewedField], **kwargs) -> None:
    current = indexed.get(kwargs["field_id"])
    if current is not None and current.proposed and not kwargs["proposed"]:
        indexed[kwargs["field_id"]] = ReviewedField(
            field_id=current.field_id,
            semantic=current.semantic,
            label=current.label,
            input_type=current.input_type,
            name=current.name,
            element_id=current.element_id,
            proposed=current.proposed,
            required=current.required,
            kind="live",
            existing=kwargs["existing"] or current.existing,
        )
        return
    indexed[kwargs["field_id"]] = ReviewedField(kind="live", **kwargs)


def _norm(value: str) -> str:
    return " ".join((value or "").replace("*", " ").casefold().split())


def _same(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()
