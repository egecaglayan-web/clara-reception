import pytest

from app.rules import cancellation_confirmed, safety
from conftest import book, email


def test_first_cancellation_email_always_requests_confirmation(engine, monkeypatch):
    book(engine)
    calls = []
    cancel = engine.calendar.cancel_appointment

    def tracked_cancel(event):
        calls.append(event.id)
        return cancel(event)

    monkeypatch.setattr(engine.calendar, "cancel_appointment", tracked_cancel)
    first = engine.process(email("cancel-first", "Please cancel my appointment."))
    assert first["status"] == "confirm_cancel"
    assert calls == []
    target = engine.calendar._events()[0]
    assert target.status == "confirmed"

    confirmation = email("cancel-confirmed", "Yes, please cancel my appointment.", first)
    assert engine.process(confirmation)["status"] == "cancelled"
    assert calls == [target.id]
    assert engine.process(confirmation)["duplicate"]
    assert calls == [target.id]


def test_cancellation_confirmation_must_reference_the_question(engine):
    booked = book(engine)
    first = engine.process(email("cancel-first", "Please cancel my appointment.", booked))
    assert first["status"] == "confirm_cancel"
    response = engine.process(email("stale-reply", "Yes, please cancel my appointment.", booked))
    assert response["status"] == "confirm_cancel"
    assert engine.calendar._events()[0].status == "confirmed"


def test_unrelated_reply_invalidates_cancellation_confirmation(engine):
    book(engine)
    first = engine.process(email("cancel-first", "Please cancel my appointment."))
    info = engine.process(email("hours", "What are your opening hours?", first))
    assert info["status"] == "info"
    response = engine.process(email("cancel-again", "Yes, please cancel my appointment.", info))
    assert response["status"] == "confirm_cancel"
    assert engine.calendar._events()[0].status == "confirmed"


def test_switching_cancellation_target_requires_a_new_question(engine):
    book(engine)
    book(engine, "second-booking", day="2026-10-30")
    listed = engine.process(email("cancel-list", "Please cancel my appointment."))
    assert listed["status"] == "which"
    info = engine.process(email("hours-before-selection", "What are your opening hours?", listed))
    assert info["status"] == "info"
    first_target = engine.process(email("select-first", "Please cancel appointment 1.", info))
    assert first_target["status"] == "confirm_cancel"
    second_target = engine.process(email("select-second", "Please cancel appointment 2.", first_target))
    assert second_target["status"] == "confirm_cancel"
    assert all(event.status == "confirmed" for event in engine.calendar._events())
    confirmed = engine.process(email("confirm-second", "Yes, please cancel.", second_target))
    assert confirmed["status"] == "cancelled"
    events = sorted(engine.calendar._events(), key=lambda event: event.start)
    assert [event.status for event in events] == ["confirmed", "cancelled"]


@pytest.mark.parametrize("confirmation_target_id,target_id,expected", [
    (None, "appointment-a", False),
    ("appointment-a", "appointment-b", False),
    ("appointment-a", "appointment-a", True),
])
def test_cancellation_confirmation_is_bound_to_target(confirmation_target_id, target_id, expected):
    assert cancellation_confirmed("Yes, please cancel.", confirmation_target_id=confirmation_target_id,
                                  target_id=target_id) is expected


@pytest.mark.parametrize("body", ["I'd feel better with a morning appointment", "after my coffee", "after choosing my costume"])
def test_safety_does_not_match_inside_benign_words(body):
    assert safety(body) is None


@pytest.mark.parametrize("body", ["I'd feel better with a morning appointment", "after my coffee"])
def test_benign_appointment_email_is_not_escalated(engine, body):
    result = engine.process(email("benign", "I'd like an appointment. " + body))
    assert result["status"] == "missing"
    assert not any(item["kind"] == "handoff" for _, item in engine.store.all("outbox"))


@pytest.mark.parametrize("body,expected", [
    ("What is the fee?", "human"),
    ("What are your fees?", "human"),
    ("What is the cost?", "human"),
    ("I have chest pain.", "emergency"),
    ("Göğüs ağrısı var.", "emergency"),
    ("Nefes alamıyorum.", "emergency"),
    ("I need another patient's appointment.", "privacy"),
    ("Reçetemi soruyorum.", "human"),
])
def test_safety_preserves_real_escalations(body, expected):
    assert safety(body) == expected
