import argparse
import sys

from app.config import DOCTORS, Settings


def check(config, smtp=False, claude=False):
    config.validate()
    print("OK: setting formats; Europe/Istanbul; weekdays 09:00–17:00; lunch 12:00–13:00; 30 minutes.")
    if config.demo:
        print("WARNING: DEMO_MODE. No external service connections or sends were made.")
        if not config.admin_token:
            print("WARNING: set ADMIN_TOKEN for the HTTP endpoints; the demo command generates its own temporary token.")
        if config.missing_live:
            print("WARNING: settings missing for live mode: " + ", ".join(x.upper() for x in config.missing_live))
        return 0
    from app.inbox import GmailInbox
    from app.mailer import SMTPMailer
    from app.calendar_service import GoogleCalendar
    from datetime import datetime, timedelta
    inbox = GmailInbox(config)
    calendar = GoogleCalendar(config)
    try:
        inbox.connect(readonly=True)
        print("OK: IMAP read-only connection.")
        now = datetime.now(config.zone)
        for doctor in DOCTORS:
            calendar.check_availability(doctor, now, now + timedelta(days=1))
            calendar._request("GET", calendar._path(doctor), params={"maxResults": 1, "timeMin": now.isoformat()})
        print("OK: availability and event reads for all three calendars.")
        if smtp:
            with SMTPMailer(config).connect():
                pass
            print("OK: SMTP login; no email was sent.")
        if claude:
            from anthropic import Anthropic
            with Anthropic(api_key=config.anthropic_api_key, timeout=config.timeout_seconds, max_retries=0) as client:
                client.messages.create(model=config.claude_model, max_tokens=10,
                                       messages=[{"role": "user", "content": "Reply OK."}])
            print("OK: short Claude connection test (billable API call).")
    finally:
        inbox.close()
        calendar.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Read-only installation check; never sends email.")
    parser.add_argument("--smtp", action="store_true")
    parser.add_argument("--claude", action="store_true")
    args = parser.parse_args()
    try:
        return check(Settings.from_env(), args.smtp, args.claude)
    except Exception:
        print("ERROR: settings or connection check failed. Check the environment settings and service access.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
