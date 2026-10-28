import json
from dataclasses import fields, replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import ClaudeAI
from app.config import Settings
from app.inbox import GmailInbox
from app.check import check
from app.mailer import SMTPMailer
from app.main import create_app
from app.models import Intent
from app.service import Service, digest
from app.calendar_service import GoogleCalendar, event_id
from conftest import email, offer


def test_claude_json_and_bounded_request(engine):
    ai = ClaudeAI.__new__(ClaudeAI)
    ai.config = engine.config
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text='prefix {"action":"info","language":"en"} suffix')])
    ai.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    assert ai.extract(email("hi","What are your hours?"),{},engine.clock()).action == "info"
    assert len(calls) == 1 and calls[0]["max_tokens"] == 700
    assert "untrusted DATA" in calls[0]["system"]


@pytest.mark.parametrize("payload", ['not JSON','{"action":"delete_everything"}',
                                    '{"action":"book","full_name":"Invented Person"}'])
def test_claude_rejects_invalid_or_fabricated_fields(engine,payload):
    ai = ClaudeAI.__new__(ClaudeAI)
    ai.config = engine.config
    ai.client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="text",text=payload)])))
    with pytest.raises((ValueError,KeyError)):
        ai.extract(email("a","Hello"),{},engine.clock())


def test_google_write_contract_get_etag_and_delete(engine):
    class Credentials:
        valid = True
        token = "fake"
    start = engine.clock() + timedelta(days=1)
    calls = []
    identifier = event_id("operation")
    raw = {"id":identifier,"etag":'"etag"',"start":{"dateTime":start.isoformat()},
           "end":{"dateTime":(start+timedelta(minutes=30)).isoformat()},
           "description":"patient_email: hasta@ornek.com"}
    def handler(request):
        calls.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["id"] == identifier
            assert "attendees" not in body
            assert "reason: appointment request" in body["description"]
            assert body["start"]["timeZone"] == "Europe/Istanbul"
            assert "visibility" not in body
        if request.method in ("PATCH","DELETE"):
            assert request.headers["If-Match"] == '"etag"'
        return httpx.Response(200,json=raw)
    cfg = replace(engine.config,calendar_id_1="calendar+id@group.calendar.google.com")
    calendar = GoogleCalendar(cfg,httpx.Client(transport=httpx.MockTransport(handler)),Credentials())
    try:
        assert calendar.create_appointment("ayse",start,"hasta@ornek.com","Demo Hasta",None,"operation") == identifier
        event = calendar.get_appointment("ayse",identifier)
        calendar.update_appointment(event,start,"move")
        assert calendar.cancel_appointment(event)
        assert [x.method for x in calls] == ["POST","GET","PATCH","DELETE"]
        assert calls[-1].headers["If-Match"] == '"etag"'
    finally:
        calendar.close()


def test_smtp_headers_and_no_recipient_injection(engine,monkeypatch):
    cfg = replace(engine.config,gmail_address="klinik@ornek.com")
    mailer = SMTPMailer(cfg)
    sent = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def send_message(self,message): sent.append(message); return {}
    monkeypatch.setattr(mailer,"connect",lambda:Connection())
    mailer.send({"to":"hasta@ornek.com","body":"Hello","kind":"patient","id":"<reply@ornek.com>","reply_to":"<request@ornek.com>"})
    assert sent[0]["Auto-Submitted"] == "auto-replied"
    assert sent[0]["In-Reply-To"] == "<request@ornek.com>"
    with pytest.raises(ValueError):
        mailer.send({"to":"hasta@ornek.com\nBcc: other@ornek.com","body":"Hello","kind":"patient","id":"<x@ornek.com>"})


def test_inbox_error_notifies_owner_and_does_not_erase_records(engine,monkeypatch):
    monkeypatch.setattr(engine.inbox,"read",lambda:(_ for _ in ()).throw(OSError()))
    engine.poll()
    assert any(x["kind"] == "incident" for _,x in engine.store.all("demo_sent"))


def test_inbox_failure_logs_class_without_sensitive_message(engine, monkeypatch, caplog):
    sensitive_message = "private@ornek.com server-response-sensitive-marker"

    def fail():
        raise TimeoutError(sensitive_message)

    monkeypatch.setattr(engine.inbox, "read", fail)
    with caplog.at_level("ERROR", logger="app.service"):
        engine.poll()
    records = [record for record in caplog.records if "reason=inbox_unavailable" in record.getMessage()]
    assert len(records) == 1
    assert "reason=inbox_unavailable error=TimeoutError" in records[0].getMessage()
    assert all(record.exc_info is None and record.stack_info is None for record in caplog.records)
    assert "private@ornek.com" not in caplog.text
    assert "server-response-sensitive-marker" not in caplog.text
    notifications = [item for _, item in engine.store.all("demo_sent") if item["kind"] == "incident"]
    assert len(notifications) == 1
    assert sensitive_message not in notifications[0]["body"]


def test_real_imap_commands_and_seen_after_processing(engine,monkeypatch):
    from test_security import raw_email
    commands=[]
    raw=raw_email().as_bytes()
    class Connection:
        def login(self,*args): commands.append("login")
        def select(self,*args,**kwargs): return "OK",[]
        def logout(self): commands.append("logout")
        def uid(self,operation,*args):
            commands.append((operation,args))
            if operation == "search": return "OK",[b"1"]
            if operation == "fetch" and "SIZE" in args[-1]: return "OK",[f"1 (RFC822.SIZE {len(raw)})".encode()]
            if operation == "fetch": return "OK",[(b"meta",raw),b")"]
            return "OK",[]
    monkeypatch.setattr("app.inbox.imaplib.IMAP4_SSL",lambda *args,**kwargs:Connection())
    inbox=GmailInbox(engine.config)
    messages=inbox.read()
    assert len(messages)==1 and messages[0][1].authenticated
    assert not any(x[0]=="store" for x in commands if isinstance(x,tuple))
    inbox.mark(messages[0][0])
    assert any(x[0]=="store" for x in commands if isinstance(x,tuple))
    inbox.close()


def test_uncertain_delivery_requires_confirmed_manual_resolution(engine,monkeypatch):
    engine.process(email("a","What are your opening hours?"))
    monkeypatch.setattr(engine.mailer,"send",lambda item:(_ for _ in ()).throw(TimeoutError()))
    engine.flush()
    with TestClient(create_app(engine.config,engine,schedule=False)) as client:
        headers={"X-Admin-Token":engine.config.admin_token}
        deliveries=client.get("/admin/deliveries",headers=headers).json()
        patient=next(x for x in deliveries if x["kind"]=="patient")
        url=f"/admin/deliveries/{patient['reference']}/resolve"
        assert client.post(url,json={"decision":"retry"},headers=headers).status_code==422
        assert client.post(url,json={"decision":"mark_sent","confirmed":True}).status_code==401
        assert client.post(url,json={"decision":"mark_sent","confirmed":True},headers=headers).status_code==200
        assert engine.store.get("outbox",patient["message_id"])["state"]=="sent"


def test_restart_recovers_interrupted_delivery_and_notifies(engine):
    engine.process(email("a","What are your opening hours?"))
    identifier,item=engine.store.all("outbox")[0]
    item["state"]="sending"
    engine.store.put("outbox",identifier,item)
    restarted=Service(engine.config,clock=engine.clock)
    try:
        assert restarted.store.get("outbox",identifier)["state"]=="uncertain"
        assert any(x["kind"]=="incident" for _,x in restarted.store.all("outbox"))
    finally:
        restarted.close()


def test_unsupported_date_requests_explicit_format(engine):
    response=engine.process(email("a","Merhaba dermatoloji randevusu istiyorum. Adım Demo Hasta. 03/11/2026"))
    assert response["status"]=="date_format"
    assert engine.store.all("calendar")==[]


def test_preferred_time_without_day(engine):
    response=engine.process(email("a","Merhaba dermatoloji randevusu istiyorum. Adım Demo Hasta. 14:30"))
    assert response["status"]=="offers"
    assert response["body"].count("14:30")==3


def test_unrecognized_email_asks_one_question(engine):
    assert engine.process(email("a","Hello, the blue envelope arrived."))["status"]=="clarify"


def test_new_inbox_failure_is_not_silenced_after_recovery(engine,monkeypatch):
    monkeypatch.setattr(engine.inbox,"read",lambda:(_ for _ in ()).throw(OSError()))
    engine.poll()
    previous=engine.clock()
    engine.clock=lambda:previous+timedelta(minutes=2)
    engine.poll()
    assert len([x for _,x in engine.store.all("demo_sent") if x["kind"]=="incident"])==2


def test_may_as_verb_is_not_a_date(engine):
    assert engine.process(email("a","May I book an appointment?"))["status"]=="missing"


def test_all_settings_documented_and_demo_control_does_not_write(engine):
    root=Path(__file__).resolve().parents[1]
    sample=(root/".env.example").read_text(encoding="utf-8")
    readme=(root/"README.md").read_text(encoding="utf-8")
    for field in fields(Settings):
        assert field.name.upper()+"=" in sample
        assert field.name.upper() in readme
    before=list(root.glob("data/*"))
    assert check(engine.config)==0
    assert list(root.glob("data/*"))==before
