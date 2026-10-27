from app.models.enums import FactType
from app.services.generation_service import retrieve_relevant_facts


class _Fact:
    def __init__(self, id, fact_type, fact_key, fact_value):
        self.id = id
        self.fact_type = fact_type
        self.fact_key = fact_key
        self.fact_value = fact_value


def test_retrieval_prefers_overlapping_project_facts():
    facts = [
        _Fact(1, FactType.SKILL, "Languages", {"items": ["English"]}),
        _Fact(2, FactType.PROJECT, "Alpha Queue", {"name": "Alpha Queue", "bullets": ["Built a job queue."]}),
        _Fact(3, FactType.WORK_EXPERIENCE, "Northwind", {"employer": "Northwind"}),
    ]
    selected = retrieve_relevant_facts(facts, "Tell us about a project you are proud of.")
    assert [f.fact_key for f in selected][0] == "Alpha Queue"


def test_retrieval_returns_nothing_when_nothing_matches():
    facts = [_Fact(1, FactType.SKILL, "Languages", {"items": ["English"]})]
    assert retrieve_relevant_facts(facts, "What is your favorite color?") == []
