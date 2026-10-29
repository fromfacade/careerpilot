"""Count what a Greenhouse session actually completed.

Hidden controls are absent from the plan. Duplicate questions count once.
A field is autofilled only after the browser read the value back.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Completion:
    total: int
    autofilled: int
    already_completed: int
    manual: int
    required_unanswered: int
    percent: int


def completion_for(plan, report) -> Completion:
    if plan is None:
        return Completion(0, 0, 0, 0, 0, 0)
    rows = _rows(plan)
    outcomes = _outcomes(plan, report)
    groups: dict[str, list[_Row]] = {}
    for row in rows.values():
        groups.setdefault(row.identity, []).append(row)
    autofilled = already = manual = required_open = 0
    for group in groups.values():
        if len(group) > 1:
            manual += 1
            if _required_open(group, outcomes):
                required_open += 1
            continue
        row = group[0]
        status = outcomes.get(row.field_id)
        if status == "filled":
            autofilled += 1
        elif status == "preserved" or (row.existing and status not in {"failed", "stale"}):
            already += 1
        else:
            manual += 1
        if row.required is True and status not in {"filled", "preserved"} and not row.existing:
            required_open += 1
    total = len(groups)
    done = autofilled + already
    percent = round(100 * done / total) if total else 0
    return Completion(total, autofilled, already, manual, required_open, percent)


@dataclass(frozen=True)
class _Row:
    field_id: str
    semantic: str
    label: str
    required: bool | None
    existing: str | None

    @property
    def identity(self) -> str:
        return f"{self.semantic}|{_norm(self.label)}"


def _rows(plan) -> dict[str, _Row]:
    rows: dict[str, _Row] = {}
    for bucket in ("ready", "clarification", "missing_required", "sensitive", "unsupported", "preserve_existing"):
        for item in getattr(plan, bucket):
            if getattr(item, "input_type", "") == "file":
                continue
            rows[item.field_id] = _Row(
                item.field_id,
                item.semantic or "",
                item.label or "",
                item.required,
                item.existing_value,
            )
    for bucket in ("matched", "missing", "ambiguous", "sensitive", "preserved"):
        for item in getattr(plan.answers, bucket):
            if item.field_id in rows:
                continue
            rows[item.field_id] = _Row(
                item.field_id,
                "custom_question",
                item.label or "",
                item.required,
                item.existing_value,
            )
    resume_id = getattr(plan.resume, "field_id", None)
    if resume_id and resume_id not in rows:
        rows[resume_id] = _Row(resume_id, "resume", plan.resume.display_name or "Resume", None, None)
    return rows


def _outcomes(plan, report) -> dict[str, str]:
    found: dict[str, str] = {}
    if report is None:
        return found
    for item in report.outcomes:
        found[item.field_id] = item.status
    resume_id = getattr(plan.resume, "field_id", None)
    if resume_id and getattr(report, "resume_status", "") == "attached":
        found[resume_id] = "filled"
    return found


def _required_open(group: list[_Row], outcomes: dict[str, str]) -> bool:
    if not any(row.required is True for row in group):
        return False
    return not any(outcomes.get(row.field_id) in {"filled", "preserved"} or row.existing for row in group)


def _norm(value: str) -> str:
    return " ".join((value or "").replace("*", " ").casefold().split())
