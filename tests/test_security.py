from dataclasses import replace
from datetime import datetime, timedelta
from email.message import EmailMessage

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.inbox import parse_email
from app.rules import candidates, eligible, owned
from app.main import create_app
from app.models import Incoming
from app.service import Service
from app.calendar_service import GoogleCalendar
from conftest import book, email


def test_sender_cannot_read_other_patient_or_hijack_thread(engine):
    result = book(engine)
    response = engine.process(email("attacker", "Please cancel my appointment.", result, "other@ornek.com"))
    assert response["status"] == "no_appointments"
    assert "Demo Hasta" not in response["body"]
    assert "09:30" not in response["body"]
    assert engine.calendar._events()[0].status == "confirmed"


def test_sender_must_be_authenticated(engine):
    result = book(engine)
    response = engine.process(email("spoofed", "Please cancel my appointment.", result, authenticated=False))
    assert response["status"] == "unverified"
    assert engine.calendar._events()[0].status == "confirmed"


def test_exact_patient_email_not_substring(engine):
    book(engine)
    event = engine.calendar._events()[0]
    assert not owned(event.model_copy(update={"description": "patient_email: otherhasta@ornek.com"}), "hasta@ornek.com")
    assert not owned(event.model_copy(update={"description": "patient_email: hasta@ornek.com\npatient_email: other@ornek.com"}), "hasta@ornek.com")


@pytest.mark.parametrize("hour,minute,expected", [(8,30,False),(9,0,True),(11,30,True),(12,0,False),
                                               (12,30,False),(13,0,True),(16,30,True),(17,0,False),(10,15,False)])
def test_hours(engine, hour, minute, expected):
    slot = datetime(2026, 10, 29, hour, minute, tzinfo=engine.config.zone)
    assert eligible(slot, engine.clock(), engine.config.zone) is expected


@pytest.mark.parametrize("day,expected", [("2026-10-28",False),("2026-10-29",True),("2026-10-31",False),
                                         ("2026-11-27",True),("2026-11-30",False)])
def test_date_window(engine, day, expected):
    slot = datetime.fromisoformat(day + "T09:00:00").replace(tzinfo=engine.config.zone)
    assert eligible(slot, engine.clock(), engine.config.zone) is expected


def test_next_three_workdays_and_naive(engine):
    now = datetime(2026, 10, 30, 10, tzinfo=engine.config.zone)
    slots = candidates(now, engine.config.zone)
    assert len({x.date() for x in slots}) == 3
    assert all(x.weekday() < 5 and x.hour != 12 for x in slots)
    assert not eligible(datetime(2026, 11, 2, 9), now, engine.config.zone)


def raw_email(body="Please book an appointment.", authenticated=True):
    message = EmailMessage()
    message["From"] = "Demo <hasta@ornek.com>"
    message["To"] = "klinik@ornek.com"
    message["Message-ID"] = "<example@ornek.com>"
    if authenticated:
        message["Authentication-Results"] = "mx.google.com; dmarc=pass header.from=ornek.com"
    message.set_content(body)
    return message


def test_email_auth_and_quoted_old_messages():
    msg = parse_email(raw_email("Please send clinic hours.\n> Please cancel my appointment.").as_bytes())
    assert msg.authenticated
    assert "cancel" not in msg.body
    assert not parse_email(raw_email(authenticated=False).as_bytes()).authenticated
    spoofed = raw_email(authenticated=False)
    spoofed["Authentication-Results"] = "evil.example; dmarc=pass header.from=ornek.com"
    assert not parse_email(spoofed.as_bytes()).authenticated


@pytest.mark.parametrize("header,value", [("Auto-Submitted","auto-replied"),("Precedence","bulk"),("List-ID","<list@ornek.com>")])
def test_email_loop_filter(header,value):
    msg = raw_email()
    msg[header] = value
    assert parse_email(msg.as_bytes()) is None


def test_email_invalid_input():
    with pytest.raises(ValueError):
        parse_email(b"x" * 131073)
    with pytest.raises(ValueError):
        parse_email(b"Subject: x\r\n\r\nhello")
    with pytest.raises(ValidationError):
        Incoming(message_id="<a@ornek.com>", sender="hasta@ornek.com\r\nBcc: evil@ornek.com", body="test")


def test_api_auth_validation_limits_and_demo_trigger(engine):
    with TestClient(create_app(engine.config, engine, schedule=False)) as client:
        headers = {"X-Admin-Token":engine.config.admin_token}
        assert client.get("/health").status_code == 401
        assert client.get("/health",headers=headers).status_code == 200
        assert client.post("/admin/poll").status_code == 401
        assert client.post("/demo/email",json={},headers=headers).status_code == 422
        assert client.post("/demo/email",content=b"x"*65537,headers=headers).status_code == 413
        data = email("http", "What are your opening hours?").model_dump()
        first = client.post("/demo/email",json=data,headers=headers)
        assert first.status_code == 200
        assert first.json()["status"] == "info"
        assert not first.json()["duplicate"]
        assert client.post("/demo/email",json=data,headers=headers).json()["duplicate"]


def test_api_chunked_oversize(engine):
    with TestClient(create_app(engine.config, engine, schedule=False)) as client:
        response = client.post("/demo/email", content=iter([b"x"*40000,b"x"*40000]),
                               headers={"X-Admin-Token":engine.config.admin_token})
        assert response.status_code == 413


def test_crash_after_side_effect_not_repeated(engine):
    message = email("crash", "Option 1 please.")
    key = engine._link_key(message.sender,message.message_id)
    engine.store.put("messages",key,{"state":"processing","root":key})
    assert engine.process(message)["status"] == "error"
    assert engine.store.all("calendar") == []
    assert engine.process(message)["duplicate"]


def test_smtp_uncertain_does_not_auto_retry(engine, monkeypatch):
    engine.process(email("hours", "What are your opening hours?"))
    calls = []
    def fail(item):
        calls.append(item)
        raise TimeoutError()
    monkeypatch.setattr(engine.mailer,"send",fail)
    engine.flush()
    engine.flush()
    assert len([x for x in calls if x["kind"] == "patient"]) == 1
    assert len([x for x in calls if x["kind"] == "incident"]) == 1
    assert engine.status()["needs_review"]


def test_demo_cannot_silently_become_live_on_same_database(engine):
    # Test the mode check before starting any real service.
    engine.store.put("meta","mode","live")
    with pytest.raises(ValueError,match="separate DATABASE_PATH"):
        Service(engine.config)
    engine.store.put("meta","mode","demo")


def test_google_freebusy_error_and_pagination(engine):
    class Credentials:
        valid = True
        token = "fake-token"
    seen = []
    def handler(request):
        seen.append(request)
        assert request.extensions["timeout"]["read"] == engine.config.timeout_seconds
        if request.url.path.endswith("/freeBusy"):
            return httpx.Response(200,json={"calendars":{"demo-calendar":{"errors":[{"reason":"notFound"}]}}})
        if request.url.params.get("pageToken") == "next":
            return httpx.Response(200,json={"items":[]})
        return httpx.Response(200,json={"items":[],"nextPageToken":"next"})
    cfg = replace(engine.config,calendar_id_1="demo-calendar",calendar_id_2="demo-calendar",calendar_id_3="demo-calendar")
    calendar = GoogleCalendar(cfg,httpx.Client(transport=httpx.MockTransport(handler)),Credentials())
    try:
        with pytest.raises(ValueError):
            calendar.check_availability("ayse",engine.clock(),engine.clock()+timedelta(days=1))
        assert calendar.list_appointments("hasta@ornek.com",engine.clock()) == []
        assert len(seen) == 7
    finally:
        calendar.close()


def test_config_demo_default_and_invalid(monkeypatch):
    assert Settings().demo
    assert replace(Settings(),demo_mode=False,live_actions_enabled=True).demo
    with pytest.raises(ValueError):
        replace(Settings(),poll_seconds=0).validate()
    monkeypatch.setenv("DEMO_MODE","maybe")
    with pytest.raises(ValueError):
        Settings.from_env()
