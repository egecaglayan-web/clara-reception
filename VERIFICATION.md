# Delivery and Verification — 28 October 2026

## Contents

- `app/`: FastAPI, the conversation state machine, Gmail/Google Calendar/Claude adapters and their demo counterparts, a persistent record/delivery queue and templates in three languages.
- `tests/`: flow, date boundaries, confirmation, ownership, redelivery, concurrency, error paths and adapter contracts.
- Setup/delivery: README, PLAN, project CLAUDE.md, `.env.example` without secrets, Dockerfile, test CI and dependency lists.
- Portfolio: `DEMO_SCRIPT.md`, a nine-email demo and `docs/demo-output.txt`.

## Offline checks

| Check | Result |
|---|---|
| Python 3.12.10 / `pytest -q` | 153 passed; no external service requests |
| `python -m app.check` | Exit 0; expected warnings for demo mode and missing live settings |
| `python -m app.demo` | Exit 0; offer, booking, reschedule, cancellation and human handoff |
| Demo languages | Turkish, English and Arabic |
| Demo delivery summary | 10 synthetic deliveries, 0 interrupted operations, no review needed |
| `pip check` | No broken dependencies |
| Scan of sources for Anthropic key / private key patterns | No matches; real secret files were not read |

The tests emit one dependency warning: Starlette's TestClient says its `httpx` compatibility will be removed. It does not affect the app and is recorded in the README.

## Live test with dedicated test accounts

Run on 28 October 2026 with a separate test Gmail account, three test calendars shared with a service account (`writerWithoutPrivateAccess`), and the Claude API (`claude-haiku-5-5`). Only the user's own addresses and synthetic patient data were used.

| Step | Result |
|---|---|
| `python -m app.check --smtp --claude` | IMAP read-only, three calendars readable, SMTP login, Claude reachable |
| Booking request → offers | Three checked slots offered; nothing written yet |
| Option chosen → booked | Event created, re-read and verified in the doctor's calendar |
| Calendar write failure | No partial record; patient got the error template; team got a handoff and an operations alert |
| "Please cancel my appointment." → confirmation question | `confirm_cancel`; calendar untouched |
| "Yes, please cancel." → cancelled | Event deleted with `If-Match`; calendar empty afterwards |
| "I have a question about my prescription." | `handoff`; team notified |
| Gmail threading | Custom Message-IDs kept by Gmail; replies stay in the same thread |

Issues found live and fixed:

- **403 on event creation:** `visibility: private` is not allowed for `writerWithoutPrivateAccess`. The field is now omitted; create/get/delete verified live afterwards.
- **Cancellation read as `clarify`:** Claude returned `clarify` for "Please cancel my appointment." in 9 of 10 calls. After the prompt fix, 30 of 30 live calls were classified correctly (cancel ×15 in English and Turkish, reschedule ×5, clarify for "Hello." ×5, human for a prescription question ×5).
- **Quoted reply headers:** the Turkish Gmail header and English headers wrapped over two lines are now stripped.
- **Inbox errors without a cause:** two transient `inbox_unavailable` events were alerted correctly but did not log the cause. The exception class is now logged, without the message.

Test events, the test database and the server were removed after the live test.

## Not verified

Docker image build, a Linux CI run, Railway deployment, delivery to external (non-Gmail) mailboxes, and use with real patients or a real clinic's calendars. These must not be presented as done or production-ready.
