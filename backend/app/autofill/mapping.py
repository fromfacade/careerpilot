"""Map detected fields to verified candidate data. Does not fill or submit.

Webpage labels are data. They are never treated as instructions. Contact
values come from active verified or edited canonical facts, then from the
single candidate profile when no canonical fact claims that field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.autofill.greenhouse import DetectedField, detect_application
from app.autofill.materials import AnswerPlan, Materials, ResumePlan, apply_materials, empty_resume

_PERSONAL = frozenset(
    {"first_name", "last_name", "email", "phone", "location", "linkedin", "github", "portfolio"}
)
_EDUCATION = frozenset({"school", "degree", "discipline"})
_FILLABLE = _PERSONAL | _EDUCATION | {"phone_country"}
_UNSUPPORTED = frozenset({"resume", "cover_letter", "custom_question", "unknown"})
_USABLE = frozenset({"verified", "edited"})
_KEY_MAP = {
    "first name": "first_name",
    "given name": "first_name",
    "last name": "last_name",
    "family name": "last_name",
    "surname": "last_name",
    "email": "email",
    "email address": "email",
    "phone": "phone",
    "phone number": "phone",
    "mobile phone": "phone",
    "location": "location",
    "current location": "location",
    "linkedin": "linkedin",
    "linkedin profile": "linkedin",
    "linkedin url": "linkedin",
    "github": "github",
    "github profile": "github",
    "github url": "github",
    "portfolio": "portfolio",
    "portfolio url": "portfolio",
    "website": "portfolio",
    "personal website": "portfolio",
}
_PROFILE_FIELDS = {
    "email": "email",
    "phone": "phone",
    "location": "location",
    "linkedin": "linkedin_url",
    "github": "github_url",
    "portfolio": "portfolio_url",
}
_REVIEW_KEYS = frozenset(
    {"needs_review", "review_reasons", "ambiguous_fields", "unclassified_text", "possible_duplicate_of"}
)
_CONSENT = (
    "i agree",
    "i certify",
    "i acknowledge",
    "i consent",
    "terms and conditions",
    "privacy policy",
    "privacy notice",
    "by checking this",
    "electronic signature",
    "e-signature",
    "legal declaration",
)
_VALUE_KEYS = ("text", "value", "url")
_MAX_CONTACT = 500


@dataclass(frozen=True)
class FactView:
    id: int
    fact_type: str
    fact_key: str
    fact_value: dict
    identity_key: str
    status: str
    verification_status: str
    needs_review: bool = False
    conflicts_with_id: int | None = None
    source_ids: tuple[int, ...] = ()
    origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileView:
    candidate_id: int
    full_name: str = ""
    email: str = ""
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    school: str | None = None
    major: str | None = None


@dataclass
class Provenance:
    kind: str
    fact_id: int | None = None
    identity_key: str | None = None
    verification_status: str | None = None
    status: str | None = None
    source_ids: list[int] = field(default_factory=list)
    origins: list[str] = field(default_factory=list)
    profile_field: str | None = None
    candidate_id: int | None = None


@dataclass
class Alternative:
    value: str
    source_kind: str
    fact_id: int | None = None
    profile_field: str | None = None


@dataclass
class PlanField:
    field_id: str
    semantic: str
    input_type: str
    label: str
    required: bool | None
    name: str
    element_id: str
    detection_confidence: str
    proposed_value: str | None
    proposed_replacement: str | None
    existing_value: str | None
    source_fact_id: int | None
    source_kind: str | None
    mapping_confidence: str
    review_required: bool
    eligible_for_fill: bool
    uncertainty: str | None
    provenance: list[Provenance] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)


@dataclass
class AutofillPlan:
    url: str
    supported: bool
    rejection_reason: str | None
    ready: list[PlanField] = field(default_factory=list)
    clarification: list[PlanField] = field(default_factory=list)
    missing_required: list[PlanField] = field(default_factory=list)
    sensitive: list[PlanField] = field(default_factory=list)
    unsupported: list[PlanField] = field(default_factory=list)
    preserve_existing: list[PlanField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    resume: ResumePlan = field(default_factory=lambda: empty_resume("No resume was considered."))
    answers: AnswerPlan = field(default_factory=AnswerPlan)


def plan_autofill(
    url: str,
    html: str,
    facts: list[FactView],
    profile: ProfileView,
    materials: Materials | None = None,
) -> AutofillPlan:
    detection = detect_application(url, html)
    plan = AutofillPlan(
        url=detection.url,
        supported=detection.supported,
        rejection_reason=detection.rejection_reason,
        warnings=list(detection.warnings),
        blockers=list(detection.blockers),
    )
    if not detection.supported:
        apply_materials(plan, detection, None)
        return plan
    for detected in detection.fields:
        item = _map_field(detected, facts, profile)
        getattr(plan, _bucket(item)).append(item)
    apply_materials(plan, detection, materials)
    return plan


def _map_field(detected: DetectedField, facts: list[FactView], profile: ProfileView) -> PlanField:
    label = _clip(detected.label, 300)
    existing = _clip(detected.current_value, _MAX_CONTACT) if detected.current_value else None
    item = PlanField(
        field_id=detected.field_id,
        semantic=detected.semantic,
        input_type=detected.input_type,
        label=label,
        required=detected.required,
        name=detected.name,
        element_id=detected.element_id,
        detection_confidence=detected.confidence,
        proposed_value=None,
        proposed_replacement=None,
        existing_value=existing,
        source_fact_id=None,
        source_kind=None,
        mapping_confidence="none",
        review_required=True,
        eligible_for_fill=False,
        uncertainty=None,
    )
    if detected.semantic == "sensitive" or _consent(label):
        item.semantic = "sensitive"
        item.uncertainty = "This question is sensitive and was left unanswered."
        return item
    if detected.input_type == "file" or detected.semantic not in _FILLABLE:
        item.uncertainty = "This control is not a supported application field."
        return item
    if detected.input_type == "select" and not detected.options:
        item.uncertainty = "This dropdown does not expose its choices, so nothing was selected."
        return item

    if detected.semantic == "phone_country":
        proposal = _phone_country_proposal(profile, detected.options)
    elif detected.semantic in _EDUCATION:
        proposal = _education_proposal(detected.semantic, facts, profile, detected.options)
    else:
        proposal = _proposal(detected.semantic, facts, profile)
        if detected.semantic == "location":
            proposal = _narrow_location(detected.label, proposal)
    item.proposed_value = proposal.value
    item.proposed_replacement = None
    item.source_fact_id = proposal.fact_id
    item.source_kind = proposal.kind
    item.provenance = proposal.provenance
    item.alternatives = proposal.alternatives
    item.uncertainty = proposal.uncertainty
    item.mapping_confidence = "none" if proposal.value is None else proposal.confidence

    if detected.confidence != "high" and proposal.value is not None and proposal.uncertainty is None:
        item.mapping_confidence = "low"
        item.uncertainty = "The field label is not reliable enough for automatic filling."
    if proposal.value and detected.options and item.uncertainty is None:
        chosen = _exact_option(proposal.value, detected.options)
        if chosen is None:
            item.proposed_value = None
            item.mapping_confidence = "low"
            item.uncertainty = f"No listed choice exactly matches the verified {_reason_name(detected.semantic)}."
        else:
            item.proposed_value = chosen
    if existing and proposal.value and _same(existing, proposal.value):
        item.proposed_value = None
        item.mapping_confidence = "none"
        item.uncertainty = "The field already contains this value."
    elif existing and proposal.value and not _same(existing, proposal.value):
        item.proposed_replacement = proposal.value
        item.proposed_value = None
        item.mapping_confidence = "low"
        item.uncertainty = "An existing value is present. Replacing it requires approval."
    elif existing and proposal.value is None:
        item.uncertainty = item.uncertainty or "The current value is kept."

    item.eligible_for_fill = (
        item.mapping_confidence == "high"
        and item.proposed_value is not None
        and item.existing_value is None
        and item.uncertainty is None
        and not item.alternatives
    )
    item.review_required = not item.eligible_for_fill
    return item


_ABSENT = frozenset(
    {
        "No verified value is available.",
        "The full name has more than two parts, so it was not split.",
        "The stored value is too long to use as a contact field.",
        "No verified degree name is available. A degree level alone was not entered.",
        "No verified phone country code is available, so the dialing country was not selected.",
    }
)


def _bucket(item: PlanField) -> str:
    if item.semantic == "sensitive":
        return "sensitive"
    if item.existing_value:
        return "preserve_existing"
    if item.semantic not in _FILLABLE or item.input_type == "file":
        return "unsupported"
    if item.eligible_for_fill:
        return "ready"
    if (
        item.required is True
        and item.proposed_value is None
        and item.proposed_replacement is None
        and item.uncertainty in _ABSENT
    ):
        return "missing_required"
    return "clarification"


@dataclass
class _Proposal:
    value: str | None = None
    confidence: str = "none"
    kind: str | None = None
    fact_id: int | None = None
    uncertainty: str | None = None
    provenance: list[Provenance] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)


def _phone_country_proposal(profile: ProfileView, options: list[str]) -> _Proposal:
    provenance = [Provenance(kind="profile", profile_field="phone", candidate_id=profile.candidate_id)]
    prefix = _dial_prefix(profile.phone)
    if not prefix:
        return _Proposal(uncertainty="No verified phone country code is available, so the dialing country was not selected.")
    matched = [option for option in options if _has_prefix(option, prefix)]
    if len(matched) == 1:
        return _Proposal(value=matched[0], confidence="high", kind="profile", provenance=provenance)
    if len(matched) > 1:
        return _Proposal(uncertainty="More than one country uses this phone prefix, so none was selected.")
    return _Proposal(uncertainty="No listed choice exactly matches the verified phone country.")


def _education_proposal(semantic: str, facts: list[FactView], profile: ProfileView, options: list[str]) -> _Proposal:
    key = {"school": "institution", "degree": "degree", "discipline": "major"}[semantic]
    usable: list[tuple[str, FactView]] = []
    held = False
    for fact in facts:
        if fact.fact_type != "education":
            continue
        raw = _edu_text(fact, key)
        if not raw:
            continue
        if _usable(fact):
            usable.append((raw, fact))
        elif fact.status != "archived":
            held = True
    distinct: list[tuple[str, list[FactView]]] = []
    for value, fact in usable:
        for existing, members in distinct:
            if _same(existing, value):
                members.append(fact)
                break
        else:
            distinct.append((value, [fact]))
    if len(distinct) > 1:
        return _Proposal(uncertainty=f"More than one verified {_reason_name(semantic)} matches this field.")
    if held and not distinct:
        return _Proposal(uncertainty="The matching education record is unverified and was not used.")
    if distinct:
        value, chosen = distinct[0]
        proposal = _Proposal(
            value=value,
            confidence="high",
            kind="canonical_fact",
            fact_id=chosen[0].id,
            provenance=[_fact_provenance(fact) for fact in chosen],
        )
    else:
        attr = {"school": "school", "discipline": "major"}.get(semantic)
        raw = getattr(profile, attr, None) if attr else None
        value = raw.strip() if isinstance(raw, str) else ""
        if not value:
            if semantic == "degree":
                return _Proposal(uncertainty="No verified degree name is available. A degree level alone was not entered.")
            return _Proposal(uncertainty="No verified value is available.")
        proposal = _Proposal(
            value=value,
            confidence="high",
            kind="profile",
            provenance=[Provenance(kind="profile", profile_field=attr, candidate_id=profile.candidate_id)],
        )
    if options:
        chosen_option = _exact_option(proposal.value or "", options)
        if chosen_option is None:
            return _Proposal(uncertainty=f"No listed choice exactly matches the verified {_reason_name(semantic)}.")
        proposal.value = chosen_option
    return proposal


def _narrow_location(label: str, proposal: _Proposal) -> _Proposal:
    if not proposal.value or proposal.uncertainty or _normalize(label) not in {"city", "location city"}:
        return proposal
    city, problem = _city_from(proposal.value)
    if problem:
        return _Proposal(uncertainty=problem, provenance=proposal.provenance)
    return _Proposal(
        value=city,
        confidence=proposal.confidence,
        kind=proposal.kind,
        fact_id=proposal.fact_id,
        provenance=proposal.provenance,
    )


def _city_from(value: str) -> tuple[str | None, str | None]:
    text = value.strip()
    if not text or any(char.isdigit() for char in text) or text.count(",") > 1:
        return None, "The verified location is not a single city."
    if text.count(",") == 1:
        city = text.split(",", 1)[0].strip()
        return (city, None) if city else (None, "The verified location is not a single city.")
    return text, None


def _dial_prefix(phone: str | None) -> str | None:
    text = (phone or "").strip()
    if not text.startswith("+"):
        return None
    digits: list[str] = []
    started = False
    for char in text[1:]:
        if char.isdigit():
            digits.append(char)
            started = True
            if len(digits) > 3:
                return None
        elif started:
            break
        elif char != " ":
            return None
    if not digits:
        return None
    return "+" + "".join(digits)


def _has_prefix(option: str, prefix: str) -> bool:
    return re.search(rf"(?<![\d+]){re.escape(prefix)}(?!\d)", option) is not None


def _exact_option(value: str, options: list[str]) -> str | None:
    matches = [option for option in options if option.strip() and _same(value, option)]
    return matches[0] if len(matches) == 1 else None


def _edu_text(fact: FactView, key: str) -> str | None:
    value = (fact.fact_value or {}).get(key)
    if isinstance(value, str) and value.strip() and len(value.strip()) <= _MAX_CONTACT:
        return value.strip()
    return None


def _reason_name(semantic: str) -> str:
    return {
        "phone_country": "phone country",
        "school": "school",
        "degree": "degree",
        "discipline": "discipline",
        "location": "location",
    }.get(semantic, "value")


def _proposal(semantic: str, facts: list[FactView], profile: ProfileView) -> _Proposal:
    matches = [fact for fact in facts if _semantic_of(fact) == semantic and (_scalar(fact) or _unclear_value(fact))]
    blocked = _blocked_ids(facts)
    conflicts = [fact for fact in matches if fact.id in blocked or fact.status == "conflict"]
    usable = [fact for fact in matches if _usable(fact) and fact.id not in blocked]
    held = [fact for fact in matches if fact not in usable and fact not in conflicts and _holds_back(fact)]
    unclear = [fact for fact in usable if _unclear_value(fact)]
    if conflicts:
        return _Proposal(
            uncertainty="Unresolved canonical facts claim this field and were not used.",
            alternatives=_fact_alternatives(conflicts),
        )
    if unclear:
        return _Proposal(uncertainty="A matching canonical fact does not have one clear value.")
    distinct = _distinct(usable)
    if len(distinct) > 1:
        return _Proposal(
            uncertainty="More than one verified value matches this field.",
            alternatives=_fact_alternatives(usable),
        )
    if held:
        disagreed = [fact for fact in held if _scalar(fact) and (not distinct or not _same(_scalar(fact) or "", distinct[0][0]))]
        if disagreed or not distinct:
            return _Proposal(
                uncertainty=_held_reason(held[0]),
                alternatives=_fact_alternatives(held),
            )
    if distinct:
        value, chosen = distinct[0]
        profile_value = _profile_value(semantic, profile)
        provenance = [_fact_provenance(fact) for fact in chosen]
        if profile_value and not _same(profile_value, value):
            field_name = "full_name" if semantic in {"first_name", "last_name"} else _PROFILE_FIELDS.get(semantic)
            return _Proposal(
                uncertainty="A verified canonical fact and the candidate profile disagree.",
                alternatives=[
                    *_fact_alternatives(chosen),
                    Alternative(profile_value, "profile", profile_field=field_name),
                ],
            )
        if profile_value:
            field_name = "full_name" if semantic in {"first_name", "last_name"} else _PROFILE_FIELDS.get(semantic)
            provenance.append(
                Provenance(kind="profile", profile_field=field_name, candidate_id=profile.candidate_id)
            )
        return _Proposal(
            value=value,
            confidence="high",
            kind="canonical_fact",
            fact_id=chosen[0].id,
            provenance=provenance,
        )
    return _from_profile(semantic, profile, facts)


def _profile_value(semantic: str, profile: ProfileView) -> str | None:
    if semantic in {"first_name", "last_name"}:
        parts = profile.full_name.split()
        if len(parts) == 1 and semantic == "first_name":
            return parts[0]
        if len(parts) == 2:
            return parts[0] if semantic == "first_name" else parts[1]
        return None
    field_name = _PROFILE_FIELDS.get(semantic)
    raw = getattr(profile, field_name, None) if field_name else None
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or len(value) > _MAX_CONTACT:
        return None
    return value


def _from_profile(semantic: str, profile: ProfileView, facts: list[FactView]) -> _Proposal:
    archived = [
        fact
        for fact in facts
        if _semantic_of(fact) == semantic and fact.status == "archived" and _scalar(fact)
    ]
    if semantic in {"first_name", "last_name"}:
        return _from_name(semantic, profile, archived)
    field_name = _PROFILE_FIELDS.get(semantic)
    raw = getattr(profile, field_name, None) if field_name else None
    value = raw.strip() if isinstance(raw, str) else None
    if not value:
        return _Proposal(uncertainty="No verified value is available.")
    if len(value) > _MAX_CONTACT:
        return _Proposal(uncertainty="The stored value is too long to use as a contact field.")
    if any(not _same(_scalar(fact) or "", value) for fact in archived):
        return _Proposal(
            uncertainty="An archived canonical fact disagrees with the profile, so neither value was chosen.",
            alternatives=[*_fact_alternatives(archived), Alternative(value, "profile", profile_field=field_name)],
        )
    return _Proposal(
        value=value,
        confidence="high",
        kind="profile",
        provenance=[
            Provenance(kind="profile", profile_field=field_name, candidate_id=profile.candidate_id)
        ],
    )


def _from_name(semantic: str, profile: ProfileView, archived: list[FactView]) -> _Proposal:
    parts = profile.full_name.split()
    if len(parts) == 1 and semantic == "first_name" and parts[0]:
        value = parts[0]
    elif len(parts) == 2:
        value = parts[0] if semantic == "first_name" else parts[1]
    elif len(parts) > 2:
        return _Proposal(uncertainty="The full name has more than two parts, so it was not split.")
    else:
        return _Proposal(uncertainty="No verified value is available.")
    if any(not _same(_scalar(fact) or "", value) for fact in archived):
        return _Proposal(
            uncertainty="An archived canonical fact disagrees with the profile, so neither value was chosen.",
            alternatives=[*_fact_alternatives(archived), Alternative(value, "profile", profile_field="full_name")],
        )
    return _Proposal(
        value=value,
        confidence="high",
        kind="profile",
        provenance=[Provenance(kind="profile", profile_field="full_name", candidate_id=profile.candidate_id)],
    )


def _usable(fact: FactView) -> bool:
    return (
        fact.status == "active"
        and fact.verification_status in _USABLE
        and not fact.needs_review
        and fact.conflicts_with_id is None
    )


def _holds_back(fact: FactView) -> bool:
    if fact.status == "archived":
        return False
    if fact.needs_review:
        return True
    return fact.verification_status not in _USABLE or fact.status != "active"


def _blocked_ids(facts: list[FactView]) -> set[int]:
    blocked: set[int] = set()
    for fact in facts:
        if fact.status == "conflict" or fact.conflicts_with_id is not None:
            blocked.add(fact.id)
            if fact.conflicts_with_id is not None:
                blocked.add(fact.conflicts_with_id)
    return blocked


def _semantic_of(fact: FactView) -> str | None:
    if fact.fact_type != "other":
        return None
    return _KEY_MAP.get(_normalize(fact.fact_key))


def _unclear_value(fact: FactView) -> bool:
    payload = {key: value for key, value in (fact.fact_value or {}).items() if key not in _REVIEW_KEYS}
    for key in _VALUE_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return len(value.strip()) > _MAX_CONTACT
    strings = [value.strip() for value in payload.values() if isinstance(value, str) and value.strip()]
    if not strings:
        return False
    return len(strings) != 1 or len(strings[0]) > _MAX_CONTACT


def _scalar(fact: FactView) -> str | None:
    payload = {key: value for key, value in (fact.fact_value or {}).items() if key not in _REVIEW_KEYS}
    for key in _VALUE_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            return text if len(text) <= _MAX_CONTACT else None
    strings = [value.strip() for value in payload.values() if isinstance(value, str) and value.strip()]
    if len(strings) == 1 and len(strings[0]) <= _MAX_CONTACT:
        return strings[0]
    return None


def _distinct(facts: list[FactView]) -> list[tuple[str, list[FactView]]]:
    groups: list[tuple[str, list[FactView]]] = []
    for fact in facts:
        value = _scalar(fact)
        if not value:
            continue
        for existing, members in groups:
            if _same(existing, value):
                members.append(fact)
                break
        else:
            groups.append((value, [fact]))
    return groups


def _fact_provenance(fact: FactView) -> Provenance:
    return Provenance(
        kind="canonical_fact",
        fact_id=fact.id,
        identity_key=fact.identity_key,
        verification_status=fact.verification_status,
        status=fact.status,
        source_ids=list(fact.source_ids),
        origins=list(fact.origins),
    )


def _fact_alternatives(facts: list[FactView]) -> list[Alternative]:
    seen: list[Alternative] = []
    for fact in facts:
        value = _scalar(fact)
        if not value:
            continue
        if any(item.fact_id == fact.id for item in seen):
            continue
        seen.append(Alternative(value=value, source_kind="canonical_fact", fact_id=fact.id))
    return seen


def _held_reason(fact: FactView) -> str:
    if fact.verification_status == "rejected":
        return "The matching canonical fact was rejected and was not used."
    if fact.verification_status == "unverified" or fact.needs_review:
        return "The matching canonical fact is unverified and was not used."
    return "The matching canonical fact is not an active verified value."


def _consent(label: str) -> bool:
    text = _normalize(label)
    return any(phrase in text for phrase in _CONSENT)


def _option_match(value: str, options: list[str]) -> bool:
    return any(_same(value, option) for option in options)


def _same(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def _normalize(value: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", value.casefold())
    return " ".join(text.split())


def _clip(value: str | None, limit: int) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else value[:limit]
