# Clara — Email Reception for a Clinic

An automation demo that can be shown to clients and added to a portfolio. Clara receives appointment requests by Gmail, checks availability in Google Calendar, and books, reschedules or cancels appointments only after an explicit choice by the patient. It writes administrative replies in Turkish, English and Arabic, and hands medical and out-of-scope topics over to the reception team's email address.

**The default demo is fully local:** no Google, Gmail or Claude account is needed and no real email is sent. The live adapters were tested end to end on 2026-10-28 with a dedicated test Gmail account, three test calendars and the Claude API (see [VERIFICATION.md](VERIFICATION.md)). This version has not been put into service for real patients.

## 1. What it does

- Weekdays 09:00–17:00, lunch break 12:00–13:00; 30-minute appointments.
- Europe/Istanbul time zone; bookings from tomorrow up to 30 days ahead.
- Offers at most three checked time slots. Never books directly from the first request.
- Re-reads and verifies the calendar event after every create and update.
- Blocks a second appointment for the same patient, doctor and day. For cancellations it first sends a separate confirmation question for the selected appointment, and cancels only after an explicit confirmation sent in reply to that question. A first email never cancels anything.
- Tracks emails and delivery state in SQLite; a repeated message is never processed twice.
- At most one human handoff per conversation; a request still unresolved after two replies is handed off.
- When an emergency is detected, it first points the patient to 112. It never gives medical advice.
- Auto-reply and bulk-mail filters prevent email loops.

| n8n step | Code equivalent |
|---|---|
| Email Trigger / Schedule | `inbox.py` / `main.py` |
| AI Agent | `ai.py`: JSON intent extraction; patient replies come from code templates |
| IF / Switch | `service.py` / `rules.py` |
| Google Calendar | `calendar_service.py` |
| Send Email | `mailer.py` |
| Error Trigger | `notifications.py` + persistent email queue |
| Executions / Memory | `store.py`: SQLite |

## 2. Try it now

Run the commands in this project folder. Python 3.12 is required:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.check
.\.venv\Scripts\python.exe -m app.demo
```

`app.demo` uses a fixed demo date (28 October 2026) and sends nine synthetic emails to the protected HTTP trigger. It shows offer → booking → reschedule → cancellation confirmation → cancellation → human handoff, in three languages. The temporary database is removed when it finishes. Expect `DEMO OK` and 10 demo deliveries in the output, one of which is a handoff to the team. The [demo script](DEMO_SCRIPT.md) can be used for a portfolio walkthrough; a sample run is in [docs/demo-output.txt](docs/demo-output.txt).

The demo parser is a limited rule engine, not a general language model; the live adapter uses Claude. Date expressions the code can verify are `YYYY-MM-DD`, weekday names, `yarın/tomorrow/غدا` and `gelecek hafta/next week`; times are `HH:MM`; a choice looks like `Seçenek 1 lütfen / Option 1 please / الخيار 1 نعم`. For any other date format Clara asks for an explicit date. Attachments are not processed; HTML-only emails go to team review.

### HTTP server

Set a persistent, non-personal admin token in your environment. For example, in PowerShell generate a new token for this session and start the app:

```powershell
$env:ADMIN_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Never put the token in a chat, the repository or a screenshot. Every HTTP endpoint requires `X-Admin-Token`; without a configured token it returns 503, with a wrong one 401. `/docs` and OpenAPI are disabled. The demo command generates its own temporary token and does not print it.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Protected liveness check |
| `GET /admin/status` | Demo mode, delivery counts, whether review is needed |
| `POST /admin/poll` | Scan the mailbox manually and process pending deliveries |
| `POST /demo/email` | Trigger a synthetic email, demo mode only |
| `GET /admin/deliveries` | Identifiers (no personal data) of pending/uncertain deliveries |
| `POST /admin/deliveries/{reference}/resolve` | Resolve a reviewed uncertain delivery |

Example demo trigger (`authenticated` is only accepted as protected local demo input; in the real IMAP flow it is computed from Gmail headers):

```json
{
  "message_id": "<demo-1@ornek.com>",
  "sender": "hasta@ornek.com",
  "body": "Hello, I'd like a dermatology appointment. My name is Demo Patient. Tomorrow 14:30",
  "authenticated": true,
  "references": []
}
```

Put the reply's `message_id` into the next email's `references`. Calling again with the same `message_id` and sender creates no new appointment and no new reply. In production there is no endpoint that injects messages; `/demo/email` returns 404.

## 3. Setting up the external services

Run the first tests only with mailboxes you own, separate test calendars and synthetic people. Enter account details yourself as environment variables or in the hosting platform's **Variables** screen. `.env` is not loaded automatically; you can load a file you prepared explicitly with the python-dotenv CLI. `.env.example` is only a settings template.

### Gmail / Google Workspace

1. Create a separate test Gmail account for the automation. Emails you read manually are skipped by the `UNSEEN` scan, so do not use your personal inbox.
2. Google Account → **Security** → turn on **2-Step Verification**.
3. If your account supports it, create an app password under **App passwords** for this automation only. Do not use your normal Google password.
4. Enter the address as `GMAIL_ADDRESS` and the app password as `GMAIL_APP_PASSWORD` yourself. Do not share the password; you can revoke it after the demo.
5. Enter a separate team/test recipient address as `TEAM_EMAIL`. It cannot be the automation mailbox; human handoffs and errors go here.
6. The default connections are IMAP SSL `imap.gmail.com:993` and SMTP SSL `smtp.gmail.com:465`. This version supports only the SSL ports.
7. If a Workspace admin blocks IMAP or app passwords, do not switch to live mode with this version. OAuth is a separate development; never try to work around the block with the normal password.

Google recommends Sign in with Google/OAuth over app passwords where possible, and the app password option may be disabled for some organization accounts. See [Google app passwords](https://support.google.com/accounts/answer/185833) and [Gmail IMAP/SMTP](https://developers.google.com/workspace/gmail/imap/imap-smtp).

Sender verification looks for an aligned `dmarc=pass` in Gmail's first `Authentication-Results` header. Without it, Clara shares no appointment information and hands over to the team. DMARC verifies the domain; it is not proof that the mailbox belongs to a real person, nor strong identity for healthcare operations. Assess your own production authentication needs separately.

### Google Calendar — three test calendars

1. Google Cloud Console → create/select a project → **APIs & Services → Library → Google Calendar API → Enable**.
2. Under **IAM & Admin → Service Accounts**, create a service account for this automation only. Do not grant broad roles such as project owner.
3. If your organization policy allows it, create a key yourself under **Keys**. Do not put the key file in the project; enter its content only as raw JSON in the `GOOGLE_SERVICE_ACCOUNT_JSON` environment variable.
4. In Google Calendar, create three separate test calendars via **Settings → Add calendar → Create new calendar**.
5. In each calendar, use **Share with specific people or groups** to give the service account address **Make changes to events** only. If an account/organization policy blocks sharing, ask the administrator.
6. Copy the **Integrate calendar → Calendar ID** values in order: `CALENDAR_ID_1` Dr. Ayşe Demir (General Practice); `CALENDAR_ID_2` Dr. Mehmet Kaya (Dermatology); `CALENDAR_ID_3` Dr. Sara Haddad (Pediatrics).

**Permission note:** Sharing with **Make changes to events** may grant the service account `writerWithoutPrivateAccess`. This role can read/write regular events but cannot access private event details; explicitly creating an event with `visibility: private` can fail with **403 Forbidden**, as observed in live tests on all three calendars. Clara therefore omits `visibility` from event creation and inherits the calendar's default visibility. Keep these calendars non-public and share them only with authorized staff and the service account. Existing private events require calendar-owner review; Clara does not modify them. See Google's [ACL role documentation](https://developers.google.com/workspace/calendar/api/v3/reference/acl) and [event visibility documentation](https://developers.google.com/workspace/calendar/api/v3/reference/events#resource).

API scopes are limited to `calendar.events` and `calendar.events.freebusy`. No attendees are added; patients are informed by SMTP. The event description contains only `patient_email`, `patient_phone`, a generic `reason: appointment request` and `booked_by`. Symptoms are never copied to the calendar. Event IDs are deterministic; updates and cancellations are protected against concurrent changes with `If-Match`. See the [Events API](https://developers.google.com/workspace/calendar/api/v3/reference/events) and the [free/busy API](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query).

### Claude / Anthropic

1. Create separate API access for this automation in the Anthropic Console, and enter the key yourself as `ANTHROPIC_API_KEY`.
2. Choose a model available to your account with `CLAUDE_MODEL`. The default `claude-haiku-5-5` comes from the official model documentation; check your account's access and the current model list. [Model documentation](https://platform.claude.com/docs/en/models/haiku-5-5/overview).
3. Set a spending limit in the Console. The code makes at most one Claude call per email, with 700 output tokens, a timeout without retries, and a daily `MAX_AI_CALLS_DAILY` limit.
4. The model only extracts a validated JSON intent. Date/time calculations, booking authority and all factual reply text come from code. An AI failure or invalid JSON produces a handoff to the team instead of a guess.

### Live-mode check and switch-on

Live mode needs every required setting, with `DEMO_MODE=false` and `LIVE_ACTIONS_ENABLED=true` set together. If anything is missing the app falls back entirely to demo mode; there is no half-live mode. Turn these flags on only when you knowingly approve real test emails and calendar writes. Run the check command first, then the server; once the server is up, scanning starts automatically every `POLL_SECONDS` seconds.

```powershell
python -m app.check --smtp
```

The check opens IMAP read-only, reads availability/events from the three calendars and, with `--smtp`, only logs in; it never creates events or emails. The optional `--claude` makes one short, billable API call. When testing with real accounts, send a few synthetic emails to your own address and clean up the test records afterwards.

### Settings

Every setting is in `app/config.py` and `.env.example`. Empty service credentials switch the demo on.

| Variable | Default / use |
|---|---|
| `DEMO_MODE` | `true`; all services are fake |
| `LIVE_ACTIONS_ENABLED` | `false`; a second explicit switch for real side effects |
| `ADMIN_TOKEN` | Empty; the user generates at least 32 characters for HTTP |
| `DATABASE_PATH` | `data/clara.sqlite`; separate files for demo and live mode |
| `TIMEZONE` | `Europe/Istanbul`; fixed for this clinic |
| `CLINIC_NAME` | `Demo Clinic`; fill in before going live |
| `CLINIC_ADDRESS` | Fictional demo address; fill in before going live |
| `CLINIC_PHONE` | `Demo phone`; fill in before going live |
| `GMAIL_ADDRESS` | Empty; automation mailbox |
| `GMAIL_APP_PASSWORD` | Empty; secret, app password |
| `TEAM_EMAIL` | Empty; separate team address |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Empty; secret, raw service account JSON |
| `CALENDAR_ID_1`, `CALENDAR_ID_2`, `CALENDAR_ID_3` | Empty; three separate doctor calendars |
| `ANTHROPIC_API_KEY` | Empty; secret |
| `CLAUDE_MODEL` | `claude-haiku-5-5`; verify access on your account |
| `TIMEOUT_SECONDS` | `20`; external connections, 1–120 |
| `POLL_SECONDS` | `60`; scan interval, 15–3600 |
| `BATCH_SIZE` | `10`; max messages per scan, 1–50 |
| `RETENTION_DAYS` | `30`; cleanup of normal conversation/delivery records, 1–365 |
| `MAX_AI_CALLS_DAILY` | `100`; cap per Istanbul calendar day, 1–10000 |
| `MAX_BODY_CHARS` | `12000`; max processable text, 100–12000 |
| `IMAP_FOLDER` | `INBOX`; unread messages only |
| `IMAP_HOST`, `IMAP_PORT` | `imap.gmail.com`, `993` |
| `SMTP_HOST`, `SMTP_PORT` | `smtp.gmail.com`, `465` |

## 4. Deployment — Railway / Docker

The project is prepared to be its own repository; it has not been deployed yet. Railway screen names may change over time; check the [current deployment docs](https://docs.railway.com/guides/dockerfiles) and [volume docs](https://docs.railway.com/guides/volumes).

1. Make this project folder the root of a separate GitHub repository; do not add `.env`, data files or keys. `.github/workflows/test.yml` only runs the tests.
2. In Railway, create a service from the repository and use the Dockerfile.
3. For the first deployment set `DEMO_MODE=true`, `LIVE_ACTIONS_ENABLED=false` and a strong `ADMIN_TOKEN`.
4. Mount a persistent volume at `/app/data` and set `DATABASE_PATH=/app/data/clara.sqlite`. The container runs as UID 10001; the volume must be writable by that user. Check that records survive a restart.
5. Use **one replica and one worker**. Several services must never share the same mailbox or calendars. Also avoid old and new consumers overlapping during rolling deploys; for the demo, stop the old one first.
6. The Docker command uses Railway's `PORT` variable. Reach the admin API only over HTTPS with the token.
7. Configure an external uptime monitor to query `/admin/status` with the `X-Admin-Token` header. If a healthcheck cannot send HTTP headers, use a TCP check instead; never make the health endpoints public.
8. Once real test permissions are granted, use a separate database and test service settings: run `app.check --smtp` first, then start the app.

On a machine with Docker:

```powershell
docker build -t clara-demo .
docker run --rm -p 8000:8000 -e DEMO_MODE=true -e ADMIN_TOKEN clara-demo
```

This command mounts no persistent disk; demo records are lost on restart. Persistent use requires a volume with the right permissions. The Docker/Railway deployment has not been run and verified in this development environment.

## 5. Handover, data and operations notes

The accounts and API spending belong to the client/user. Check prices and daily sending limits in each service's current documentation; no cost or uptime commitment is made here. Locked dependencies are in `requirements.lock`; after any version upgrade, rerun the tests, the check and the demo.

### Uncertain delivery or interrupted operation

SMTP delivery and the local commit are not one atomic operation. If the response is lost, the email may have been sent. `sending/uncertain` states are **never resent automatically**. `needs_review=true` on `/admin/status` should raise an alert. When a patient delivery fails, an operations alert email is also queued; if SMTP is completely down that alert is delayed too, so external uptime/status monitoring is needed.

Find the identifier with `GET /admin/deliveries`. After checking delivery by Message-ID in the Sent folder, send one of these decisions to the protected resolve endpoint:

```json
{"decision": "mark_sent", "confirmed": true}
```

If it is certain that the email was not delivered, choose `decision: retry`; `POST /admin/poll` then sends it. Choosing retry without knowing the outcome can produce a duplicate email. A calendar operation interrupted in the `processing` state is never re-executed; a person reviews the calendar and the original email and contacts the patient manually. An event already written to the calendar is not rolled back automatically if a later step fails.

### Privacy and limits

The raw email text is never copied to logs or the database. The message is held in memory for processing, and in live mode it is sent to Claude for intent extraction. The database holds the patient's address, if needed their name/phone, appointment preferences, template replies and delivery states. The calendar description holds email/phone; no medical details are stored. Disk encryption, backups and access control are the operator's responsibility. Normal records are deleted after the retention period; uncertain operations and calendar events are never deleted automatically and need human review or a separate retention policy.

Because health and children's data may arrive, review KVKK/GDPR, international data transfers, provider agreements, patient identity and retention policy with a lawyer before real use. This repository contains no legal text. Use only synthetic scenarios in a portfolio.

Natural-language safety detection is not perfect; the demo is not an emergency assessment or clinical triage system. Public holidays are not handled. Not every race caused by people editing the calendar at the same time can be prevented. Moving to production for a clinic requires separate identity verification, load testing and an operations review.

In the test environment, the Starlette version emits a deprecation warning about TestClient's `httpx` compatibility; the tests pass. This is not a real HTTP sending error; the test client migration can be handled together with a dependency upgrade.

## 6. Folder structure

```text
app/                    Settings, flow, services, language templates, check and demo
tests/                  Offline flow, security and adapter tests
docs/demo-output.txt    Sample demo run
.github/workflows/      Test-only CI
.env.example            Settings template without secrets
requirements.txt        Allowed direct dependencies
requirements.lock       Verified full dependency versions
Dockerfile              Python 3.12, single worker
PLAN.md                 Approved scope and design
VERIFICATION.md         What was verified offline and with live test accounts
CLAUDE.md               Rules for an assistant taking over the project
DEMO_SCRIPT.md          Portfolio presentation order
```

## 7. Ideas for further development

Gmail OAuth, broader date expressions, a public-holiday calendar, an authenticated patient portal and Redis/PostgreSQL-based multi-instance coordination can be added as separate scopes. These features are not in the current scope and must not be presented as if the demo already had them.
