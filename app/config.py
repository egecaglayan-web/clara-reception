import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    demo_mode: bool = True
    live_actions_enabled: bool = False
    admin_token: str = ""
    database_path: str = "data/clara.sqlite"
    timezone: str = "Europe/Istanbul"
    clinic_name: str = "Demo Clinic"
    clinic_address: str = "Demo address — presentation only"
    clinic_phone: str = "Demo phone"
    gmail_address: str = ""
    gmail_app_password: str = ""
    team_email: str = ""
    google_service_account_json: str = ""
    calendar_id_1: str = ""
    calendar_id_2: str = ""
    calendar_id_3: str = ""
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-5-5"
    timeout_seconds: int = 20
    poll_seconds: int = 60
    batch_size: int = 10
    retention_days: int = 30
    max_ai_calls_daily: int = 100
    max_body_chars: int = 12000
    imap_folder: str = "INBOX"
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465

    @property
    def zone(self):
        return ZoneInfo(self.timezone)

    @property
    def required_live(self):
        return ("gmail_address", "gmail_app_password", "team_email",
                "google_service_account_json", "calendar_id_1", "calendar_id_2",
                "calendar_id_3", "anthropic_api_key", "admin_token")

    @property
    def missing_live(self):
        return [name for name in self.required_live if not getattr(self, name).strip()]

    @property
    def demo(self):
        return self.demo_mode or not self.live_actions_enabled or bool(self.missing_live)

    def validate(self):
        self.zone
        if self.timezone != "Europe/Istanbul":
            raise ValueError("This clinic uses the Europe/Istanbul time zone.")
        for value, low, high in ((self.timeout_seconds, 1, 120), (self.poll_seconds, 15, 3600),
                                 (self.batch_size, 1, 50), (self.retention_days, 1, 365),
                                 (self.max_ai_calls_daily, 1, 10000), (self.max_body_chars, 100, 12000)):
            if not low <= value <= high:
                raise ValueError("A numeric setting is outside its allowed range.")
        if not self.database_path.strip():
            raise ValueError("DATABASE_PATH cannot be empty.")
        if not self.demo:
            from app.models import email_address
            for address in (self.gmail_address, self.team_email):
                email_address(address)
            if len(self.admin_token) < 32:
                raise ValueError("ADMIN_TOKEN must be at least 32 characters.")
            if len({self.calendar_id_1, self.calendar_id_2, self.calendar_id_3}) != 3:
                raise ValueError("Each doctor needs a separate calendar.")
            if self.gmail_address.casefold() == self.team_email.casefold():
                raise ValueError("The team address must differ from the automation mailbox.")
            if "Demo" in self.clinic_name or "Demo" in self.clinic_phone or "Demo" in self.clinic_address:
                raise ValueError("Fill in the clinic details for live mode.")
        if self.imap_port != 993 or self.smtp_port != 465:
            raise ValueError("This version uses IMAP SSL 993 and SMTP SSL 465.")

    @classmethod
    def from_env(cls):
        defaults = cls()
        values = {}
        for name in cls.__dataclass_fields__:
            raw = os.environ.get(name.upper())
            if raw is None:
                continue
            default = getattr(defaults, name)
            if isinstance(default, bool):
                if raw.lower() not in ("true", "false", "1", "0"):
                    raise ValueError(f"{name.upper()} must be true/false.")
                values[name] = raw.lower() in ("true", "1")
            elif isinstance(default, int):
                values[name] = int(raw)
            else:
                values[name] = raw
        result = cls(**values)
        result.validate()
        return result


DOCTORS = {
    "ayse": ("Dr. Ayşe Demir", "General Practice", "calendar_id_1"),
    "mehmet": ("Dr. Mehmet Kaya", "Dermatology", "calendar_id_2"),
    "sara": ("Dr. Sara Haddad", "Pediatrics", "calendar_id_3"),
}
