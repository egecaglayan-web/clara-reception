import hashlib
import logging
import re
import threading
from datetime import datetime, timedelta

from app.ai import ClaudeAI, DemoAI, parse_day
from app.notifications import handoff_body, incident_body
from app.store import Store
from app.inbox import DemoInbox, GmailInbox
from app.rules import cancellation_confirmed, candidates, eligible, exact_choice, folded, language, owned, safety
from app.mailer import DemoMailer, SMTPMailer
from app.texts import appointment_details, clinic_info, format_date, render, text
from app.models import Intent
from app.calendar_service import DemoCalendar, GoogleCalendar

logger = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Service:
    def __init__(self, config, *, store=None, calendar=None, mailer=None, ai=None, inbox=None, clock=None):
        config.validate()
        # Keep HTTP clients' INFO/DEBUG URL and body logs from leaking patient or service data.
        for name in ("httpx", "httpcore", "anthropic", "urllib3", "google.auth.transport.requests"):
            logging.getLogger(name).setLevel(logging.WARNING)
        self.config = config
        self.store = store or Store(config.database_path)
        mode = "demo" if config.demo else "live"
        previous = self.store.get("meta", "mode")
        if previous and previous != mode:
            if store is None:
                self.store.close()
            raise ValueError("Use a separate DATABASE_PATH for demo and live mode.")
        self.store.put("meta", "mode", mode)
        self.calendar = calendar or (DemoCalendar(self.store) if config.demo else GoogleCalendar(config))
        self.mailer = mailer or (DemoMailer(self.store) if config.demo else SMTPMailer(config))
        self.ai = ai or (DemoAI() if config.demo else ClaudeAI(config))
        self.inbox = inbox or (DemoInbox() if config.demo else GmailInbox(config))
        self.clock = clock or (lambda: datetime.now(config.zone))
        self.lock = threading.RLock()
        for identifier, delivery in self.store.all("outbox"):
            if delivery["state"] == "sending":
                delivery["state"] = "uncertain"
                self.store.put("outbox", identifier, delivery)
                self.incident(digest(identifier), "interrupted_delivery")
        for key, message in self.store.all("messages"):
            if message["state"] == "processing":
                self.incident(key, "interrupted_operation")

    def _link_key(self, sender, message_id):
        return digest(sender + "\0" + message_id)

    def _thread(self, message):
        if not message.authenticated:
            return self._link_key(message.sender, message.message_id)
        for reference in reversed(message.references):
            root = self.store.get("links", self._link_key(message.sender, reference))
            if root:
                return root
        return self._link_key(message.sender, message.message_id)

    def _queue(self, key, to, body, kind, reply_to=None):
        identifier = "<" + digest(key) + "@clara.local>"
        if self.store.get("outbox", identifier) is None:
            self.store.put("outbox", identifier, {"id": identifier, "to": to, "body": body,
                           "kind": kind, "reply_to": reply_to, "state": "pending"})
        return identifier

    def incident(self, reference, reason, *, error=None):
        if error is None:
            logger.error("operation_requires_review reference=%s reason=%s", reference[:12], reason)
        else:
            logger.error("operation_requires_review reference=%s reason=%s error=%s",
                         reference[:12], reason, type(error).__name__)
        self._queue("incident:" + reference + reason, self.config.team_email or "ekip@ornek.com",
                    incident_body(reference, reason), "incident")

    def flush(self):
        with self.lock:
            for identifier, item in self.store.all("outbox"):
                if item["state"] != "pending":
                    continue
                item["state"] = "sending"
                self.store.put("outbox", identifier, item)
                try:
                    self.mailer.send(item)
                except Exception:
                    # The SMTP response may have been lost; an automatic resend could create a duplicate email.
                    item["state"] = "uncertain"
                    self.store.put("outbox", identifier, item)
                    logger.error("email_delivery_uncertain delivery=%s", digest(identifier)[:12])
                    if item["kind"] == "patient":
                        self.incident(digest(identifier), "email_delivery_uncertain")
                    # The same SMTP path may be down; the alert stays queued and is also visible in status.
                    continue
                item["state"] = "sent"
                self.store.put("outbox", identifier, item)

    def _handoff(self, state, action, reason, kind="handoff"):
        if state.get("escalated"):
            return "already", ""
        state.update(escalated=True, handoff_pending={"action": action, "reason": reason})
        return kind, ""

    def process(self, message):
        with self.lock:
            key = self._link_key(message.sender, message.message_id)
            existing = self.store.get("messages", key)
            if existing and existing["state"] == "done":
                return {**existing["result"], "duplicate": True}
            root = existing.get("root", self._thread(message)) if existing else self._thread(message)
            state = self.store.get("threads", root, {})
            lang = language(message.body)
            if len(message.body.split()) <= 4 and state.get("language") and not safety(message.body):
                lang = state["language"]
            now = self.clock()
            if now.utcoffset() is None:
                raise ValueError("A clock without a time zone cannot be used.")
            if existing:
                # The previous run may have stopped after a side effect. Calendar writes are not repeated.
                kind, details = self._handoff(state, "unknown", "interrupted_operation", "error")
                self.incident(key, "interrupted_operation")
            else:
                self.store.put("messages", key, {"state": "processing", "root": root})
                try:
                    if len(message.body) > self.config.max_body_chars:
                        raise ValueError("Message limit exceeded.")
                    forced = safety(message.body)
                    if forced == "emergency":
                        first = not state.get("escalated")
                        self._handoff(state, "emergency", "emergency")
                        kind, details = "emergency", text("handoff", lang) if first else ""
                    elif not message.authenticated:
                        first = not state.get("escalated")
                        self._handoff(state, "unknown", "sender_not_authenticated")
                        kind, details = "unverified", text("handoff", lang) if first else ""
                    elif state.get("escalated"):
                        kind, details = "already", ""
                    elif forced == "privacy":
                        kind, details = "privacy", ""
                    elif forced == "human":
                        kind, details = self._handoff(state, "human", "out_of_scope")
                    else:
                        budget_key = now.astimezone(self.config.zone).date().isoformat()
                        budget = self.store.get("ai_budget", budget_key, {"count": 0})
                        if budget["count"] >= self.config.max_ai_calls_daily:
                            kind, details = self._handoff(state, "unknown", "ai_daily_limit")
                        else:
                            self.store.put("ai_budget", budget_key, {"count": budget["count"] + 1, "state": "counted"})
                            try:
                                intent = Intent.model_validate(self.ai.extract(message, state, now))
                            except Exception:
                                intent = Intent(action="human", language=lang)
                                self.incident(key, "ai_unavailable_or_invalid")
                            lang = intent.language
                            kind, details = self._route(message, intent, state, now, key)
                except Exception:
                    self.incident(key, "calendar_or_processing_error")
                    kind, details = self._handoff(state, "unknown", "tool_error", "error")
            state["language"] = lang
            if kind in ("missing", "clarify", "which", "range", "unavailable", "offers", "confirm_cancel", "no_appointments", "date_format"):
                state["unresolved"] = state.get("unresolved", 0) + 1
                if state["unresolved"] > 2:
                    kind, details = self._handoff(state, state.get("pending", "unknown"), "two_unresolved_replies")
            else:
                state["unresolved"] = 0
            body = render(self.config, lang, kind, state.get("full_name") if message.authenticated else None, details)
            response_id = self._queue("reply:" + key, message.sender, body, "patient", message.message_id)
            if kind == "confirm_cancel":
                state["cancel_confirmation"] = {"target_id": state["target_id"], "message_id": response_id}
            else:
                state.pop("cancel_confirmation", None)
            # The patient reply is queued first, so emergency guidance goes out before the team alert.
            handoff = state.pop("handoff_pending", None)
            if handoff:
                self._queue("handoff:" + root, self.config.team_email or "ekip@ornek.com",
                            handoff_body(message.sender, handoff["action"], handoff["reason"]), "handoff")
            result = {"status": kind, "body": body, "message_id": response_id, "duplicate": False}
            self.store.put("threads", root, state)
            self.store.put("links", key, root)
            self.store.put("links", self._link_key(message.sender, response_id), root)
            self.store.put("messages", key, {"state": "done", "root": root, "result": result})
            logger.info("message_processed status=%s reference=%s", kind, key[:12])
            return result

    def _route(self, message, intent, state, now, key):
        if intent.action in ("human", "emergency"):
            first = not state.get("escalated")
            self._handoff(state, intent.action, "out_of_scope")
            return ("emergency", text("handoff", intent.language) if first else "") if intent.action == "emergency" else ("handoff", "")
        if intent.action == "privacy":
            return "privacy", ""
        if intent.action == "clarify":
            return "clarify", ""
        if intent.action == "info":
            return "info", clinic_info(self.config, intent.language)
        # The AI cannot invent personal data. A previous sender name is not accepted as the patient name.
        if intent.full_name:
            if intent.full_name not in message.body or len(intent.full_name.split()) < 2:
                return "missing", text("full_name", intent.language)
            state["full_name"] = intent.full_name
        if intent.phone and intent.phone in message.body:
            state["phone"] = intent.phone
        if intent.doctor:
            if intent.doctor != state.get("doctor"):
                state.pop("offers", None)
            state["doctor"] = intent.doctor
        action = intent.action
        if state.get("pending") != action:
            state.pop("offers", None)
            state.pop("target_id", None)
            state.pop("target_etag", None)
            state.pop("preferred_day", None)
            state.pop("preferred_time", None)
        state["pending"] = action
        incoming_day = parse_day(message.body, now)
        incoming_clock = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", message.body)
        # Never treat a date the model inferred from natural language as a hard fact.
        # For other numeric formats and month names, ask for the explicit format instead of guessing.
        from app.texts import MONTHS
        month_words = [folded(x) for values in MONTHS.values() for x in values]
        unsupported_date = (not incoming_day and (intent.day is not None
                            or re.search(r"\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b", message.body)
                            or any(re.search(r"\b\d{1,2}\s+" + re.escape(month) + r"(?!\w)|(?<!\w)" + re.escape(month)
                                             + r"\s+\d{1,2}\b", folded(message.body)) for month in month_words)))
        if unsupported_date:
            return "date_format", ""
        if incoming_day:
            state["preferred_day"] = incoming_day
            if not incoming_clock:
                state.pop("preferred_time", None)
        if incoming_clock:
            state["preferred_time"] = f"{int(incoming_clock[1]):02}:{incoming_clock[2]}"
        if action in ("reschedule", "cancel"):
            # Every returned record is re-checked for ownership, even with the fake service.
            appointments = [x for x in self.calendar.list_appointments(message.sender, now)
                            if owned(x, message.sender) and x.start > now and x.status != "cancelled"]
            if not appointments:
                return "no_appointments", ""
            target = self._target(message, appointments, state)
            if target is None:
                state["appointments"] = [x.id for x in appointments[:30]]
                return "which", "\n".join(f"{i + 1}. {appointment_details(self.config, x, intent.language)}"
                                           for i, x in enumerate(appointments[:30]))
            if state.get("target_id") == target.id and state.get("target_etag") and state["target_etag"] != target.etag:
                return self._handoff(state, action, "appointment_changed_during_conversation")
            state["target_id"] = target.id
            state["target_etag"] = target.etag
            state["doctor"] = target.doctor
            if action == "cancel":
                confirmation = state.get("cancel_confirmation", {})
                confirmation_target_id = (confirmation.get("target_id")
                                          if confirmation.get("message_id") in message.references else None)
                if not cancellation_confirmed(message.body, confirmation_target_id=confirmation_target_id,
                                              target_id=target.id):
                    return "confirm_cancel", appointment_details(self.config, target, intent.language)
                if not self.calendar.cancel_appointment(target):
                    raise RuntimeError("Cancellation was not verified.")
                state.pop("target_id", None)
                state["pending"] = None
                state.pop("appointments", None)
                return "cancelled", ""
        else:
            target = None
        required = ("doctor", "full_name") if action == "book" else ("doctor",)
        missing = [field for field in required if not state.get(field)]
        if missing:
            return "missing", ", ".join(text(x, intent.language) for x in missing)
        doctor = state["doctor"]
        choice = self._chosen(message, state)
        if choice is not None:
            if not eligible(choice, now, self.config.zone):
                state.pop("offers", None)
                return "range", ""
            appointments = [x for x in self.calendar.list_appointments(message.sender, now) if owned(x, message.sender)]
            if any(x.doctor == doctor and x.start.astimezone(self.config.zone).date() == choice.date()
                   and (not target or x.id != target.id) for x in appointments):
                return "duplicate", ""
            busy = self.calendar.check_availability(doctor, choice, choice + timedelta(minutes=30))
            if busy:
                state.pop("offers", None)
                return "unavailable", ""
            if target:
                identifier = self.calendar.update_appointment(target, choice, key)
            else:
                identifier = self.calendar.create_appointment(doctor, choice, message.sender, state["full_name"], state.get("phone"), key)
            # After a create/update, the first external call must always be this read.
            verified = self.calendar.get_appointment(doctor, identifier)
            if (verified.id != identifier or verified.doctor != doctor or verified.start != choice
                    or verified.end != choice + timedelta(minutes=30) or not owned(verified, message.sender)
                    or verified.status == "cancelled"):
                raise RuntimeError("Calendar write could not be verified.")
            state.pop("offers", None)
            state.pop("target_id", None)
            state["pending"] = None
            return "rescheduled" if target else "booked", appointment_details(self.config, verified, intent.language)
        day = state.get("preferred_day")
        preferred_time = state.get("preferred_time")
        try:
            slots = candidates(now, self.config.zone, day)
        except ValueError:
            return "range", ""
        if day and preferred_time:
            requested = datetime.fromisoformat(day + f"T{preferred_time}:00").replace(tzinfo=self.config.zone)
            if not eligible(requested, now, self.config.zone):
                return "range", ""
            slots = [requested]
        elif preferred_time:
            slots = [slot for slot in slots if slot.strftime("%H:%M") == preferred_time]
        if not slots:
            return "range", ""
        busy = self.calendar.check_availability(doctor, slots[0], slots[-1] + timedelta(minutes=30))
        free = [slot for slot in slots if not any(start < slot + timedelta(minutes=30) and end > slot for start, end in busy)][:3]
        if not free:
            state.pop("offers", None)
            return "unavailable", ""
        state["offers"] = [{"doctor": doctor, "start": x.isoformat()} for x in free]
        return "offers", "\n".join(f"{i + 1}. {format_date(slot, intent.language, self.config.zone)} — {self._doctor_name(doctor)}"
                                    for i, slot in enumerate(free))

    @staticmethod
    def _doctor_name(doctor):
        from app.config import DOCTORS
        return DOCTORS[doctor][0]

    def _target(self, message, appointments, state):
        # Only a list number parsed by code from the previous list; the AI cannot choose an event ID.
        match = re.search(r"(?:appointment|randevu|الموعد)\s*#?([1-9]\d?)\b", message.body, re.I)
        if len(set(re.findall(r"(?:appointment|randevu|الموعد)\s*#?([1-9]\d?)\b", message.body, re.I))) > 1:
            return None
        identifier = state.get("target_id")
        if match:
            index = int(match[1]) - 1
            saved = state.get("appointments", [])
            if index >= len(saved):
                return None
            identifier = saved[index]
        if identifier:
            return next((x for x in appointments if x.id == identifier), None)
        return appointments[0] if len(appointments) == 1 else None

    def _chosen(self, message, state):
        if not exact_choice(message.body):
            return None
        if re.search(r"\bor\b|\bveya\b|\byahut\b|أو", folded(message.body)):
            return None
        offers = [x for x in state.get("offers", []) if x["doctor"] == state.get("doctor")]
        selections = re.findall(r"(?:option|slot|secenek|seçenek|الخيار)\s*([1-3])\b", message.body, re.I)
        if len(set(selections)) > 1:
            return None
        match = re.search(r"(?:option|slot|secenek|seçenek|الخيار)\s*([1-3])\b", message.body, re.I)
        if match:
            index = int(match[1]) - 1
            if index >= len(offers):
                return None
            selected = datetime.fromisoformat(offers[index]["start"])
            day = parse_day(message.body, self.clock())
            return selected if not day or selected.date().isoformat() == day else None
        clock = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", message.body)
        if not clock or len(set(re.findall(r"\b\d{1,2}:\d{2}\b", message.body))) != 1:
            return None
        day = parse_day(message.body, self.clock())
        matches = [datetime.fromisoformat(x["start"]) for x in offers
                   if datetime.fromisoformat(x["start"]).strftime("%H:%M") == f"{int(clock[1]):02}:{clock[2]}"
                   and (not day or datetime.fromisoformat(x["start"]).date().isoformat() == day)]
        return matches[0] if len(matches) == 1 else None

    def poll(self):
        with self.lock:
            try:
                for uid, message in self.inbox.read():
                    if isinstance(message, Exception):
                        self.incident(digest(str(uid) + self.clock().isoformat()), "email_parse_error")
                    elif message is not None and message.sender != self.config.gmail_address.casefold():
                        self.process(message)
                    self.inbox.mark(uid)
            except Exception as error:
                self.incident(digest("inbox:" + self.clock().isoformat()), "inbox_unavailable", error=error)
            finally:
                self.inbox.close()
            self.flush()
            self.store.prune(self.config.retention_days)

    def status(self):
        counts = {}
        for _, item in self.store.all("outbox"):
            state = "uncertain" if item["state"] == "sending" else item["state"]
            counts[state] = counts.get(state, 0) + 1
        interrupted = sum(item["state"] == "processing" for _, item in self.store.all("messages"))
        return {"demo": self.config.demo, "deliveries": counts, "interrupted": interrupted,
                "needs_review": bool(counts.get("uncertain") or interrupted)}

    def deliveries_for_review(self):
        with self.lock:
            return [{"reference": digest(identifier), "message_id": identifier, "kind": item["kind"], "state": item["state"]}
                    for identifier, item in self.store.all("outbox") if item["state"] in ("uncertain", "sending", "pending")]

    def resolve_delivery(self, reference, decision):
        with self.lock:
            for identifier, item in self.store.all("outbox"):
                if digest(identifier) == reference and item["state"] in ("uncertain", "sending"):
                    item["state"] = "sent" if decision == "mark_sent" else "pending"
                    self.store.put("outbox", identifier, item)
                    return True
            return False

    def close(self):
        self.inbox.close()
        for item in (self.calendar, self.ai):
            if hasattr(item, "close"):
                item.close()
        self.store.close()
