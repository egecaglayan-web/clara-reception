# Clara — Email Reception for a Clinic

## Goal

Handle incoming patient emails in Turkish, English or Arabic, and create, reschedule or cancel Google Calendar appointments only with verified availability and an explicit patient choice; hand everything else over to reception.

Status: the user approved the plan on 28 October 2026. This is a low-volume demo project to show to clients and later add to a portfolio. The live adapters were tested with dedicated test accounts on 28 October 2026 (see `VERIFICATION.md`); there has been no production deployment.

## Flow

1. Email trigger → sender and message ID checks → auto-reply/loop filter → persistent duplicate check.
2. Conversation history scoped to the sender → one bounded Claude call for structured intent and field extraction → schema and permission checks in code.
3. Missing details are requested in a single reply. Known clinic information comes from settings. Ambiguous or invalid AI output falls back to a safe clarification request or a human handoff.
4. New appointment: availability check → at most three options → the patient explicitly chooses one time → scan the patient's existing appointments → re-check availability under the lock → create → re-read the same event and verify doctor, patient and time → reply.
5. Reschedule: find only the sender's appointments → settle the target appointment and the new time → same-day duplicate and availability checks → update → re-read and verify the event → reply.
6. Cancellation: find only the sender's appointments → ask which one if there are several → always send a separate confirmation question for the selected appointment → explicit confirmation in reply to that question for the same appointment → cancel → reply based on the service result.
7. Emergency: point to 112 without medical advice. Medical questions, prescriptions, results, payment, insurance, complaints or a request for a person: hand off to reception. A conversation still unresolved after two replies is handed off.
8. Error path: no guesses and no fake success messages → safe status message to the patient → alert to the owner. One human handoff per conversation; later technical errors are tracked with separate operations alerts that contain no personal data.

## n8n → file mapping

| n8n equivalent | File and responsibility |
|---|---|
| Email Trigger + Schedule | `app/inbox.py`: read incoming email; `app/main.py`: scheduler and protected manual trigger |
| AI Agent | `app/ai.py`: Claude and demo implementations, validated JSON, call limit and fallback |
| IF / Switch / connections | `app/service.py`: conversation flow and operation order |
| Code | `app/rules.py`: working hours, date range, language and appointment rules |
| Google Calendar | `app/calendar_service.py`: real/demo availability, listing, create, read, update, cancel |
| Send Email | `app/mailer.py`: real/demo patient replies and delivery state |
| Error Trigger / human handoff | `app/notifications.py`: team alert bodies, sent through the email queue |
| Executions / Wait | `app/store.py`: SQLite messages, conversations, operation state and delivery queue |
| Credentials / settings | `app/config.py`: environment variables, demo detection and validation |
| Installation check | `app/check.py`: read-only connection/settings check |
| Reply templates | `app/texts.py`: patient replies and date formats in three languages |

## Accounts and settings

- Email provider: Gmail / Google Workspace with IMAP/SMTP and an app password. Patient replies, handoffs to reception and error alerts all go by email.
- The user enters the three doctors' Google Calendar IDs and the service account key in their own environment. Doctors: Dr. Ayşe Demir / General Practice, Dr. Mehmet Kaya / Dermatology, Dr. Sara Haddad / Pediatrics.
- The user enters Anthropic API access, the clinic name/address/phone and the team alert address in their own environment. Demo defaults are a fictional clinic and synthetic patients; no real client or patient data goes into the portfolio.
- `.env` and key files are never read or created by the assistants. The delivery contains only `.env.example`, without real secrets.
- Protected admin access, the SQLite file path and a persistent disk are configured for the app. With missing service settings, the demo runs without any real service call.

## Assumptions and decisions

- The source rules apply: Europe/Istanbul, Monday–Friday 09:00–17:00, lunch 12:00–13:00; 30-minute appointments; from tomorrow up to 30 days ahead.
- Dates and times are computed by code with an explicit time zone. ISO dates, weekday names, "tomorrow" and "next week" are supported; for a date the code cannot verify, Clara asks for an explicit format. Replies are in the patient's language; dates show the weekday, day, month name, year and time.
- No appointment is created without the patient's explicit choice of a time in the current conversation.
- Patients are matched by the exact `patient_email` field in the event description and the sender; substring matches are not used. Other patients' calendar data never goes into the AI input or a patient reply.
- The email sender alone is not strong authentication. Change or cancellation requests that cannot be verified, or that arrive on someone else's behalf, are not processed automatically.
- The AI only extracts intent and candidate fields; permissions, availability, explicit choice/confirmation and side-effect decisions are verified in code. Factual clinic details and success messages come from verified service results.
- Sending policy chosen by the user: verified appointment replies and known clinic information are sent automatically; all other topics are handed over to reception. A general draft/approval screen is out of scope.
- One app instance and one uvicorn worker. A final check guards against concurrent human edits in the calendar; Google Calendar is not assumed to provide an absolute conflict lock.
- SQLite and calendar operation markers protect against restarts and redelivery. If an error follows a side effect, the operation is never blindly repeated; it is reconciled or handed to a person. Uncertain email deliveries are tracked separately.
- Raw emails and medical details are never logged; conversation data is kept to a minimum with a configurable retention period. Because health and children's data may be involved, the data flow and KVKK/GDPR obligations must be reviewed with a lawyer before live use; no legal text is produced.
- The goal is a client demo and portfolio piece with a small number of test emails. The first end-to-end demo is fully local. Real-account tests use separate test mailboxes/calendars and synthetic data only, and real sending and calendar writes need explicit approval.

## Out of scope

- Diagnosis, treatment, medication advice, interpreting test results and taking payments.
- Managing third parties' appointments, processing documents/attachments, WhatsApp and phone calls.
- Connecting to real (non-test) accounts or emailing real people; these need separate explicit approval.
- Multiple servers/workers, a clinical information system and a public patient portal.

## Delivery and verification

FastAPI/Python project with real and demo implementations for every external service, README, project CLAUDE.md, `.env.example`, Dockerfile and test-only CI. Tests run offline and cover happy paths plus service/AI failures, authorization, privacy, redelivery, restarts, date boundaries and explicit patient confirmation. The delivery checks are `pytest -q`, `python -m app.check` and the end-to-end demo email trigger. `app/demo.py` and `DEMO_SCRIPT.md` replay booking, rescheduling, cancellation and handoff with nine synthetic emails for a portfolio presentation.

Implementation details: `.env` is not loaded automatically; Gmail uses an app password and OAuth is out of scope for this version. Protected review/resolve endpoints handle uncertain SMTP deliveries. Reproducible dependencies are in `requirements.lock`.

## Changes after review and live testing

- **Cancellation confirmation:** cancellation requires a separate confirmation for the same appointment, sent in reply to the preceding confirmation question; any other reply invalidates that context.
- **Safety keywords:** matched with leading word boundaries and suffixes, with an optional Arabic `ال` and normalized Arabic stems (such as `نتايج`). `fee/cost` stay limited to singular/plural so `feel/coffee/costume` are not escalated. `real person` / `speak to someone` count as human requests.
- **Calendar visibility:** event `visibility` is omitted on creation so calendars shared as `writerWithoutPrivateAccess` work.
- **Intent classification:** the Claude prompt states that the action is the patient's goal; missing appointment, date or confirmation must not turn a clear booking/cancellation/reschedule request into `clarify`. If Claude still returns `clarify`, explicit appointment keywords shared with the demo parser are used. All selection/confirmation gates stay in the service. No `temperature` parameter (the model rejects it).
- **Quoted replies:** Turkish Gmail reply headers and English `On ... wrote:` headers wrapped over two lines are stripped before intent extraction.
- **Inbox failure logging:** `inbox_unavailable` logs the exception class only; exception messages and tracebacks stay out of logs and alert emails.
- **Language:** client-facing files, file names, comments, log and error messages are in English. Patient reply templates and keyword patterns stay in Turkish, English and Arabic.
