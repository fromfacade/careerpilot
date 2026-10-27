from app.services.answer_service import is_sensitive_category, question_fingerprint
from app.models.enums import AnswerCategory


def test_equivalent_questions_share_a_fingerprint():
    a = question_fingerprint("Why are you interested in this position?")
    b = question_fingerprint("  why are you interested in this position  ")
    assert a == b == "why are you interested in this position"


def test_empty_or_punctuation_only_is_empty():
    assert question_fingerprint("   ???   ") == ""


def test_sensitive_categories_are_explicit():
    assert is_sensitive_category(AnswerCategory.WORK_AUTHORIZATION)
    assert is_sensitive_category(AnswerCategory.SALARY)
    assert not is_sensitive_category(AnswerCategory.INTEREST)
    assert not is_sensitive_category(AnswerCategory.SKILLS)
