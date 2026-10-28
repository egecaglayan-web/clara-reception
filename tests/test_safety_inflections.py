import pytest

from app.rules import safety
from conftest import email


ESCALATION_CASES = [
    ("Şiddetli kanamam var", "emergency"),
    ("I have chest pains", "emergency"),
    ("الانتحار", "emergency"),
    ("İnsanla görüşmek istiyorum", "human"),
    ("Bir insana bağlanabilir miyim", "human"),
    ("أريد الوصفة الطبية", "human"),
    ("أين النتائج؟", "human"),
    ("أريد التحدث مع الموظف", "human"),
    ("I want to talk to a real person", "human"),
    ("Can I speak to someone?", "human"),
]


@pytest.mark.parametrize("body,expected", ESCALATION_CASES)
def test_safety_detects_inflections_and_arabic_articles(body, expected):
    assert safety(body) == expected


@pytest.mark.parametrize("body,expected", ESCALATION_CASES)
def test_inflected_requests_follow_the_escalation_workflow(engine, body, expected):
    result = engine.process(email("inflected-request", body))
    assert result["status"] == ("emergency" if expected == "emergency" else "handoff")
    if expected == "emergency":
        assert "112" in result["body"]
    assert len([item for _, item in engine.store.all("outbox") if item["kind"] == "handoff"]) == 1
    assert engine.store.all("calendar") == []


@pytest.mark.parametrize("body", ["feel", "coffee", "costume"])
def test_financial_keywords_do_not_match_benign_prefixes_or_substrings(body):
    assert safety(body) is None


def test_plural_costs_still_escalates():
    assert safety("What are the costs?") == "human"


@pytest.mark.parametrize("body,expected", [
    ("انتحار", "emergency"),
    ("وصفة", "human"),
    ("نتائج", "human"),
    ("موظف", "human"),
])
def test_arabic_article_is_optional(body, expected):
    assert safety(body) == expected
