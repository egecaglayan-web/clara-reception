import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.models import email_address

logger = logging.getLogger(__name__)


class DemoMailer:
    def __init__(self, store):
        self.store = store

    def send(self, item):
        self.store.put("demo_sent", item["id"], item)
        logger.info("demo_email_sent kind=%s delivery=%s", item["kind"], item["id"][:12])


class SMTPMailer:
    def __init__(self, config):
        self.config = config

    def connect(self):
        connection = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port,
                                      timeout=self.config.timeout_seconds, context=ssl.create_default_context())
        try:
            connection.login(self.config.gmail_address, self.config.gmail_app_password)
        except Exception:
            connection.close()
            raise
        return connection

    def send(self, item):
        message = EmailMessage()
        message["From"] = email_address(self.config.gmail_address)
        message["To"] = email_address(item["to"])
        message["Subject"] = "Clara | Reception" if item["kind"] != "patient" else "Clara | Appointment"
        message["Message-ID"] = item["id"]
        message["Auto-Submitted"] = "auto-replied" if item["kind"] == "patient" else "auto-generated"
        if item.get("reply_to"):
            message["In-Reply-To"] = item["reply_to"]
            message["References"] = item["reply_to"]
        message.set_content(item["body"])
        with self.connect() as connection:
            rejected = connection.send_message(message)
            if rejected:
                raise RuntimeError("SMTP rejected the recipient.")
