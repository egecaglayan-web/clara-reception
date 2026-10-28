import json
from types import SimpleNamespace

import pytest

from app.ai import ClaudeAI
from app.inbox import parse_email
from conftest import book, email
from test_security import raw_email


def fake_claude(engine, action="clarify"):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps({"action": action, "language": "en"}))])

    client = SimpleNamespace(messages=SimpleNamespace(create=create), close=lambda: None)
    return ClaudeAI(engine.config, client=client), calls


@pytest.mark.parametrize("body,expected", [
    ("Please cancel my appointment.", "cancel"),
    ("Please move my appointment to another day.", "reschedule"),
    ("I'd like an appointment.", "book"),
    ("Randevumu iptal etmek istiyorum.", "cancel"),
    ("Randevumu değiştirmek istiyorum.", "reschedule"),
    ("Randevu almak istiyorum.", "book"),
    ("أريد إلغاء موعدي", "cancel"),
    ("أريد تغيير موعدي", "reschedule"),
    ("أريد حجز موعد", "book"),
])
def test_claude_clarify_uses_explicit_appointment_intent(engine, body, expected):
    ai, calls = fake_claude(engine)
    result = ai.extract(email("intent", body), {}, engine.clock())
    assert result.action == expected
    assert result.language == "en"
    assert result.full_name is None and result.day is None and not result.confirmed
    assert len(calls) == 1
    assert "temperature" not in calls[0]


@pytest.mark.parametrize("body", ["Hello.", "I have some questions.", "I found my notebook."])
def test_ambiguous_claude_intent_stays_clarify(engine, body):
    ai, _ = fake_claude(engine)
    assert ai.extract(email("unclear", body), {"pending": "cancel"}, engine.clock()).action == "clarify"


@pytest.mark.parametrize("action", ["human", "emergency", "privacy", "info", "reschedule"])
def test_intent_fallback_does_not_override_other_model_actions(engine, action):
    ai, _ = fake_claude(engine, action)
    assert ai.extract(email("other-action", "Please cancel my appointment."), {}, engine.clock()).action == action


def test_clarify_fallback_keeps_separate_cancellation_confirmation(engine):
    book(engine)
    engine.ai, _ = fake_claude(engine)
    first = engine.process(email("cancel-first", "Please cancel my appointment."))
    assert first["status"] == "confirm_cancel"
    assert engine.calendar._events()[0].status == "confirmed"
    second = engine.process(email("cancel-confirm", "Yes, please cancel my appointment.", first))
    assert second["status"] == "cancelled"


def test_clarify_fallback_reschedule_without_date_does_not_move_event(engine):
    book(engine)
    original = engine.calendar._events()[0]
    engine.ai, _ = fake_claude(engine)
    result = engine.process(email("reschedule", "Please move my appointment to another day."))
    assert result["status"] == "offers"
    assert engine.calendar._events()[0] == original


@pytest.mark.parametrize("header", [
    "<klinik@ornek.com> adresine sahip kullanıcı 28 Eki 2026 Çar, 15:01\ntarihinde şunu yazdı:",
    "Demo Klinik <klinik@ornek.com> adresine sahip kullanıcı 28 Eki 2026 Çar, 15:01 tarihinde şunu yazdı:",
    "On Wed, 28 Oct 2026 at 15:01, Demo <klinik@ornek.com>\nwrote:",
    "On Wed, 28 Oct 2026 at 15:01, Demo\n<klinik@ornek.com> wrote:",
    "On Wed, 28 Oct 2026 at 15:01, Demo <klinik@ornek.com> wrote:",
])
def test_parse_email_strips_reply_header_and_old_content(header):
    current = "Option 1 please.\nMy name is Demo Patient."
    message = parse_email(raw_email(current + "\n\n" + header + "\nPlease cancel my appointment.\nI have chest pain.").as_bytes())
    assert message.body == current
    assert message.authenticated


def test_parse_email_preserves_new_text_with_on_without_reply_header():
    current = "Please move my appointment.\nOn Friday I can arrive at 10:30.\nMy name is Demo Patient."
    assert parse_email(raw_email(current).as_bytes()).body == current
