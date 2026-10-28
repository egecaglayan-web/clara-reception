# Portfolio Demo Script — Clara

Every person and clinic detail in this demo is synthetic. No real patient, client data, mailbox or API key is shown. The local demo does not connect to Google, Gmail or Claude.

## One command

Run `python -m app.demo` in the project folder.

## 3–5 minute walkthrough

1. **Problem:** availability checks, back-and-forth emails and calendar entries for reception emails are all done by hand.
2. **Offer:** an email saying "I'd like a dermatology appointment. My name is Demo Patient. 2026-10-29" (sent in Turkish in the demo) returns three available options; nothing is booked yet.
3. **Booking:** the reply "Option 2 please, I confirm" is booked at 09:30 after re-checking availability and duplicates. No success message is sent before the event is read back.
4. **Reschedule:** the patient asks for 30 October 14:30. The new time is offered; after an explicit choice the existing event is moved and read back.
5. **Cancellation:** the first request returns a confirmation question; after "Yes, I confirm the cancellation" the calendar cancellation is verified.
6. **Human handoff:** a prescription question is not answered; a separate demo email to reception is prepared instead.
7. **Languages:** English and Arabic clinic-information questions are answered in the same language.
8. **Proof:** the last line is `DEMO OK`; the status summary shows 10 synthetic deliveries and zero interrupted operations.

The demo clock is fixed at 28 October 2026 so the dates are reproducible. Public holidays are out of scope. `docs/demo-output.txt` is a synthetic sample output from the same command.

## Portfolio description

I built a Gmail-based clinic appointment automation demo with Python/FastAPI. The system extracts intent from patient emails, checks availability in the doctor's calendar and acts only on an explicit patient choice. It re-verifies the calendar event after every create or update. It includes SQLite duplicate protection, a persistent delivery queue, replies in three languages and handoff to reception. It comes with a demo that needs no external services and offline tests, and it was tested end to end with dedicated Gmail, Google Calendar and Claude test accounts.

## Say clearly while presenting

- The demo's intent extraction is rule-based; the real Claude adapter runs in live mode.
- Deliveries shown locally are not real SMTP deliveries.
- Live testing used dedicated test accounts only; Docker and Railway deployment have not been verified.
- API keys, patient data and screenshots of client accounts are never added to the portfolio.
