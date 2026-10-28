"""python -m app.demo: offline portfolio scenario using synthetic data only."""
import logging
import secrets
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.service import Service


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with tempfile.TemporaryDirectory(prefix="clara-demo-") as folder:
        config = replace(Settings(), database_path=str(Path(folder) / "demo.sqlite"), admin_token=secrets.token_urlsafe(32))
        now = datetime(2026, 10, 28, 10, 0, tzinfo=config.zone)
        engine = Service(config, clock=lambda: now)
        try:
            with TestClient(create_app(config, engine, schedule=False)) as client:
                headers = {"X-Admin-Token": config.admin_token}
                previous = None
                def send(identifier, body, sender="hasta@ornek.com", follow=True):
                    nonlocal previous
                    data = {"message_id": f"<{identifier}@ornek.com>", "sender": sender, "body": body,
                            "authenticated": True, "references": [previous] if follow and previous else []}
                    response = client.post("/demo/email", json=data, headers=headers)
                    response.raise_for_status()
                    result = response.json()
                    previous = result["message_id"]
                    print(f"\n--- {identifier}: {result['status']} ---\n{result['body']}")
                    return result
                assert send("offer", "Merhaba, dermatoloji randevusu istiyorum. Adım Demo Hasta. 2026-10-29")['status'] == 'offers'
                assert send("choice", "Seçenek 2 lütfen, onaylıyorum.")['status'] == 'booked'
                assert send("reschedule", "Randevumu değiştirmek istiyorum. 2026-10-30 14:30")['status'] == 'offers'
                assert send("new-time", "Seçenek 1 lütfen, onaylıyorum.")['status'] == 'rescheduled'
                assert send("cancel-request", "Randevu iptal")['status'] == 'confirm_cancel'
                assert send("cancel-confirm", "Evet, iptal işlemini onaylıyorum.")['status'] == 'cancelled'
                assert send("human", "Reçete hakkında bilgi istiyorum.", "diger@ornek.com", follow=False)['status'] == 'handoff'
                assert send("english", "Hello, what are your opening hours?", "english@ornek.com", follow=False)['status'] == 'info'
                assert send("arabic", "مرحبا، ما عنوان العيادة؟", "arabic@ornek.com", follow=False)['status'] == 'info'
                print("\nDEMO OK: offers, booking, rescheduling, cancellation, human handoff and three languages verified.")
                print(client.get("/admin/status", headers=headers).json())
        finally:
            engine.close()


if __name__ == "__main__":
    main()
