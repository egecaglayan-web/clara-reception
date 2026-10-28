import socket
from dataclasses import replace
from datetime import datetime

import pytest

from app.config import Settings
from app.models import Incoming
from app.service import Service


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    # Windows asyncio socketpair setup needs a loopback connection.
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def guarded(original):
        def connect(sock, address):
            if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
                return original(sock, address)
            raise AssertionError("Tests must not reach the network.")
        return connect
    monkeypatch.setattr(socket.socket, "connect", guarded(original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(original_connect_ex))


@pytest.fixture
def engine(tmp_path):
    cfg = replace(Settings(), database_path=str(tmp_path / "demo.sqlite"), admin_token="test-token-" + "x" * 32)
    service = Service(cfg, clock=lambda: datetime(2026, 10, 28, 10, tzinfo=cfg.zone))
    yield service
    service.close()


def email(identifier, body, previous=None, sender="hasta@ornek.com", authenticated=True):
    return Incoming(message_id=f"<{identifier}@ornek.com>", sender=sender, body=body,
                    references=[previous["message_id"]] if previous else [], authenticated=authenticated)


def offer(engine, identifier="offer", sender="hasta@ornek.com", day="2026-10-29", previous=None):
    return engine.process(email(identifier, f"Merhaba, dermatoloji randevusu istiyorum. Adım Demo Hasta. {day}", previous, sender))


def book(engine, identifier="book", sender="hasta@ornek.com", day="2026-10-29"):
    proposed = offer(engine, identifier + "-offer", sender, day)
    assert proposed["status"] == "offers"
    return engine.process(email(identifier, "Seçenek 2 lütfen, onaylıyorum.", proposed, sender))
