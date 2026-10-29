"""Match a verified school or degree to one employer option.

The stored fact is not changed. An option is selected only when one listed
choice is the same institution, degree type, or degree level. Majors stay
exact. Different campuses and different degree types stay different.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SCHOOL_GROUPS = {
    "ucsc": ("ucsc", "uc santa cruz", "university of california santa cruz"),
    "ucb": ("uc berkeley", "university of california berkeley"),
    "ucla": ("ucla", "uc los angeles", "university of california los angeles"),
    "ucsd": ("ucsd", "uc san diego", "university of california san diego"),
    "ucd": ("uc davis", "university of california davis"),
    "uci": ("uci", "uc irvine", "university of california irvine"),
    "ucsb": ("ucsb", "uc santa barbara", "university of california santa barbara"),
    "ucr": ("uc riverside", "university of california riverside"),
    "ucm": ("uc merced", "university of california merced"),
}
_DEGREE_TYPES = (
    ("bs", "bachelor", ("bs", "b s", "bsc", "b sc", "bachelor of science")),
    ("ba", "bachelor", ("ba", "b a", "bachelor of arts")),
    ("ms", "master", ("ms", "m s", "msc", "m sc", "master of science")),
    ("ma", "master", ("ma", "m a", "master of arts")),
    ("phd", "doctorate", ("phd", "ph d", "dphil", "doctor of philosophy")),
)
_DEGREE_LEVELS = (
    ("bachelor", ("bachelors", "bachelors degree", "bachelor degree")),
    ("master", ("masters", "masters degree", "master degree")),
    ("doctorate", ("doctorate", "doctoral degree", "doctoral")),
)
_NOUN = {"school": "school", "degree": "degree", "discipline": "major"}


@dataclass(frozen=True)
class ChoiceMatch:
    option: str | None
    explanation: str


def structured_kind(label: str) -> str | None:
    """The education meaning of a control label, when it has one."""
    text = _fold(label)
    if "degree" in text.split() or text in {"highest level of education", "education level", "degree level"}:
        return "degree"
    if "highest level of education" in text or "education level" in text or "degree level" in text:
        return "degree"
    words = set(text.split())
    if words & {"school", "university", "college"} and "diploma" not in words:
        return "school"
    if words & {"major", "discipline", "concentration"} or "field of study" in text:
        return "discipline"
    return None


def match_choice(kind: str, verified: str, options: list[str], label: str = "") -> ChoiceMatch:
    """Return the one employer option equivalent to a verified value."""
    noun = _NOUN.get(kind, "value")
    verified = (verified or "").strip()
    listed = [option.strip() for option in options if option and option.strip()]
    if not verified or not listed:
        return ChoiceMatch(None, f"No listed choice exactly matches the verified {noun}.")
    if kind == "school":
        matched = [option for option in listed if _same_school(verified, option)]
    elif kind == "degree":
        matched = [option for option in listed if _same_degree(verified, option, label)]
    elif kind == "discipline":
        matched = [option for option in listed if _fold(verified) == _fold(option)]
    else:
        matched = [option for option in listed if verified.casefold() == option.casefold()]
    if len(matched) == 1:
        chosen = matched[0]
        if chosen.casefold() == verified.casefold():
            return ChoiceMatch(chosen, "")
        return ChoiceMatch(chosen, f"Selected {chosen} because it matches your verified {noun}: {verified}.")
    if len(matched) > 1:
        return ChoiceMatch(None, f"More than one listed choice matches the verified {noun} {verified}, so none was selected.")
    return ChoiceMatch(None, f"No listed choice exactly matches the verified {noun}.")


def _same_school(verified: str, option: str) -> bool:
    left = _school_key(verified)
    right = _school_key(option)
    if left and right:
        return left == right
    return bool(left is None and right is None and _fold_school(verified) == _fold_school(option))


def _school_key(value: str) -> str | None:
    return _SCHOOL_INDEX.get(_fold_school(value))


def _same_degree(verified: str, option: str, label: str) -> bool:
    verified_type, verified_level = _degree_parts(verified)
    option_type, option_level = _degree_parts(option)
    if _asks_for_level(label):
        if not verified_level or verified_level != option_level:
            return False
        return option_type is None or option_type == verified_type
    return bool(verified_type and verified_type == option_type)


def _asks_for_level(label: str) -> bool:
    return "level" in _fold(label).split()


def _degree_parts(value: str) -> tuple[str | None, str | None]:
    folded = _fold(value)
    for key, level, aliases in _DEGREE_TYPES:
        for alias in aliases:
            if folded == alias or folded.startswith(alias + " "):
                return key, level
    for level, aliases in _DEGREE_LEVELS:
        if folded in aliases:
            return None, level
    return None, None


def _fold(value: str) -> str:
    text = (value or "").casefold().replace("'", "").replace("’", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _fold_school(value: str) -> str:
    words = [word for word in _fold(value).split() if word not in {"the", "at"}]
    joined: list[str] = []
    letters: list[str] = []
    for word in words:
        if len(word) == 1:
            letters.append(word)
            continue
        if letters:
            joined.append("".join(letters))
            letters = []
        joined.append(word)
    if letters:
        joined.append("".join(letters))
    return " ".join(joined)


_SCHOOL_INDEX = {name: ident for ident, names in _SCHOOL_GROUPS.items() for name in names}
