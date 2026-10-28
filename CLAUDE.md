# Clara project rules

This is a portfolio demo with synthetic data, to be shown to clients.
Live adapters were tested with dedicated test accounts only; there is no real clinic use.
Never put secrets, real patient data or `.env` in the repository, code, tests or logs.

## Flow
Gmail IMAP → sender/message checks → persistent duplicate check → intent extraction.
Code rules → Google Calendar operation → read-back → persistent SMTP queue.
Medical/out-of-scope request or error → email handoff to reception.
The demo runs the same flow with a SQLite calendar and recorded demo emails.

## File map
- `app/config.py`: environment settings, doctor directory, live/demo selection.
- `app/models.py`: bounded input, intent and event schemas.
- `app/main.py`: protected HTTP endpoints, scheduler lifespan.
- `app/service.py`: state machine, lock, daily AI budget, queue.
- `app/ai.py`: Claude JSON extraction and the limited demo parser.
- `app/rules.py`: ownership, confirmation, working hours and safety gates.
- `app/calendar_service.py`: Google Calendar REST and the persistent demo calendar.
- `app/inbox.py`: Gmail IMAP, MIME filters, quote stripping and the demo inbox.
- `app/mailer.py`: SMTP SSL and demo deliveries.
- `app/notifications.py`: team alerts without raw patient messages.
- `app/store.py`: SQLite state, retention.
- `app/texts.py`: code templates and date formats in three languages.
- `app/check.py`: read-only installation check.
- `app/demo.py`: end-to-end presentation with nine synthetic emails.
- `tests/`: network block, flow, privacy and service contracts.

## Project invariants
- The `patient_email:` description field must appear exactly once and match the sender.
- A calendar search result alone is not proof of ownership.
- The first external call after `create/update` must be `get_appointment`.
- The AI cannot grant write authority through `confirmed`, `day`, `time` or an event ID.
- Claude action represents intent, not readiness. Only validated `clarify` results may use the shared explicit appointment-intent rules; service selection/confirmation gates still apply. Do not add `temperature` (the model rejects it).
- Strip Turkish Gmail and wrapped English reply headers before intent extraction so quoted requests cannot change the current intent.
- Code only applies an explicit choice of a single time already offered in the conversation.
- A new appointment is never written from the first email; times are offered first.
- Cancellation requires a preceding `confirm_cancel` reply for the same `target_id`, referenced by the confirmation email. Other replies invalidate that context.
- Safety stems use leading word boundaries, suffix matching, and optional Arabic `ال`; keep `fee/cost` singular/plural only to exclude `feel/coffee/costume`. Match Arabic stems against normalized input.
- Patient templates and keyword patterns stay in Turkish, English and Arabic; everything else is in English.
- A `processing` record is never blindly re-executed after a restart.
- A `sending/uncertain` email is never resent automatically; a person reviews the outcome.
- The human handoff key is the conversation root; operations alerts are kept separate.
- Conversation references are hashed together with the sender; another sender cannot take over a thread.
- Demo and live mode cannot share the same SQLite file.
- Each of the three doctors has a separate calendar; moving an appointment to another doctor is not supported.
- Events are created without `visibility`; calendars are shared as `writerWithoutPrivateAccess`.

## Commands
In the project folder with a Python 3.12 environment:
`pip install -r requirements.lock`
`pytest -q`
`python -m app.check`
`python -m app.demo`
`uvicorn app.main:app --workers 1 --no-access-log`
Live-mode check: `python -m app.check --smtp` (sends nothing).
`--claude` is a short, billable test; only when explicitly requested.

## Known pitfalls
- The IMAP seen flag can also be changed by the user; use a separate test mailbox.
- If an email has no plain-text part, a team alert is created instead of automatic processing.
- DMARC verifies the domain; it is not strong patient authentication.
- Human edits in the calendar mean not every external race can be prevented.
- The SQLite volume must be writable by UID 10001.
- Templates claim success only with facts verified by code.
- `.env` is not loaded automatically; the user manages environment variables.
- The demo parser is not a general language model; it supports ISO dates, weekdays and "tomorrow".
- Claude intent extraction is nondeterministic; measure prompt changes over several live calls, not one.
- Secrets, raw messages and SMTP/Google error contents are never added to logs.
