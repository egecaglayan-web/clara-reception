import hashlib
import json
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx

from app.config import DOCTORS
from app.rules import owned
from app.models import Event


def event_id(key):
    return hashlib.sha256(key.encode()).hexdigest()


def description(sender, phone):
    return (f"patient_email: {sender}\npatient_phone: {phone or 'not provided'}\n"
            "reason: appointment request\nbooked_by: AI receptionist")


class DemoCalendar:
    def __init__(self, store):
        self.store = store

    def _events(self):
        return [Event.model_validate(x) for _, x in self.store.all("calendar")]

    def check_availability(self, doctor, start, end):
        return [(x.start, x.end) for x in self._events()
                if x.doctor == doctor and x.status != "cancelled" and x.start < end and x.end > start]

    def list_appointments(self, sender, now):
        return sorted([x for x in self._events() if x.start > now and x.status != "cancelled" and owned(x, sender)],
                      key=lambda x: (x.start, x.doctor, x.id))

    def create_appointment(self, doctor, start, sender, name, phone, key):
        identifier = event_id(key)
        saved = self.store.get("calendar", identifier)
        if saved:
            return identifier
        event = Event(id=identifier, doctor=doctor, start=start, end=start + timedelta(minutes=30),
                      description=description(sender, phone), summary=f"Appointment – {name} – {DOCTORS[doctor][0]}", etag="1")
        self.store.put("calendar", identifier, event.model_dump(mode="json"))
        return identifier

    def get_appointment(self, doctor, identifier):
        event = Event.model_validate(self.store.get("calendar", identifier))
        if event.doctor != doctor:
            raise ValueError("Calendar mismatch.")
        return event

    def update_appointment(self, event, start, key):
        current = self.get_appointment(event.doctor, event.id)
        if current.etag != event.etag or current.status == "cancelled":
            raise ValueError("The event was changed by another operation.")
        changed = current.model_copy(update={"start": start, "end": start + timedelta(minutes=30), "etag": str(int(event.etag) + 1)})
        self.store.put("calendar", event.id, changed.model_dump(mode="json"))
        return event.id

    def cancel_appointment(self, event):
        current = self.get_appointment(event.doctor, event.id)
        if current.etag != event.etag:
            raise ValueError("The event was changed by another operation.")
        self.store.put("calendar", event.id, current.model_copy(update={"status": "cancelled"}).model_dump(mode="json"))
        return True


class GoogleCalendar:
    def __init__(self, config, client=None, credentials=None):
        self.config = config
        self.client = client or httpx.Client(timeout=config.timeout_seconds)
        if credentials is None:
            from google.oauth2.service_account import Credentials
            credentials = Credentials.from_service_account_info(
                json.loads(config.google_service_account_json),
                scopes=["https://www.googleapis.com/auth/calendar.events",
                        "https://www.googleapis.com/auth/calendar.events.freebusy"])
        self.credentials = credentials

    def _request(self, method, path, **kwargs):
        if not self.credentials.valid:
            from google.auth.transport.requests import Request
            request = Request()
            def bounded_request(url, method="GET", body=None, headers=None, **ignored):
                return request(url=url, method=method, body=body, headers=headers, timeout=self.config.timeout_seconds)
            self.credentials.refresh(bounded_request)
        headers = {"Authorization": "Bearer " + self.credentials.token, **kwargs.pop("headers", {})}
        response = self.client.request(method, "https://www.googleapis.com/calendar/v3" + path,
                                       headers=headers, timeout=self.config.timeout_seconds, **kwargs)
        response.raise_for_status()
        return response

    def _path(self, doctor, identifier=None):
        calendar = getattr(self.config, DOCTORS[doctor][2])
        path = "/calendars/" + quote(calendar, safe="") + "/events"
        return path + ("/" + quote(identifier, safe="") if identifier else "")

    def _event(self, doctor, raw):
        return Event(id=raw["id"], doctor=doctor,
                     start=datetime.fromisoformat(raw["start"]["dateTime"]),
                     end=datetime.fromisoformat(raw["end"]["dateTime"]),
                     description=raw.get("description", ""), summary=raw.get("summary", ""),
                     etag=raw["etag"], status=raw.get("status", "confirmed"))

    def check_availability(self, doctor, start, end):
        calendar = getattr(self.config, DOCTORS[doctor][2])
        result = self._request("POST", "/freeBusy", json={"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                               "timeZone": self.config.timezone, "items": [{"id": calendar}]}).json()
        entry = result["calendars"][calendar]
        if entry.get("errors") or "busy" not in entry:
            raise ValueError("Could not read calendar availability.")
        return [(datetime.fromisoformat(x["start"]), datetime.fromisoformat(x["end"])) for x in entry["busy"]]

    def list_appointments(self, sender, now):
        # The server-side search narrows candidates; ownership is still verified by exact field match.
        events = []
        for doctor in DOCTORS:
            params = {"q": sender, "timeMin": now.isoformat(), "singleEvents": "true", "maxResults": 250,
                      "timeZone": self.config.timezone}
            for _ in range(40):
                result = self._request("GET", self._path(doctor), params=params).json()
                for raw in result.get("items", []):
                    if "dateTime" not in raw.get("start", {}) or raw.get("status") == "cancelled":
                        continue
                    event = self._event(doctor, raw)
                    if event.start > now and owned(event, sender):
                        events.append(event)
                if not result.get("nextPageToken"):
                    break
                params["pageToken"] = result["nextPageToken"]
            else:
                raise ValueError("Calendar pagination limit exceeded.")
        return sorted(events, key=lambda x: (x.start, x.doctor, x.id))

    def _times(self, start):
        start = start.astimezone(self.config.zone)
        return {"start": {"dateTime": start.isoformat(), "timeZone": self.config.timezone},
                "end": {"dateTime": (start + timedelta(minutes=30)).isoformat(), "timeZone": self.config.timezone}}

    def create_appointment(self, doctor, start, sender, name, phone, key):
        identifier = event_id(key)
        # Inherit calendar visibility; writerWithoutPrivateAccess cannot manage private events.
        body = {"id": identifier, **self._times(start), "summary": f"Appointment – {name} – {DOCTORS[doctor][0]}",
                "description": description(sender, phone),
                "extendedProperties": {"private": {"booked_by": "clara", "operation": event_id(key)}}}
        result = self._request("POST", self._path(doctor), params={"sendUpdates": "none"}, json=body).json()
        if result["id"] != identifier:
            raise ValueError("Event ID mismatch.")
        return identifier

    def get_appointment(self, doctor, identifier):
        return self._event(doctor, self._request("GET", self._path(doctor, identifier)).json())

    def update_appointment(self, event, start, key):
        # If-Match prevents overwriting an appointment a person changed in the meantime.
        result = self._request("PATCH", self._path(event.doctor, event.id), headers={"If-Match": event.etag},
                               params={"sendUpdates": "none"}, json={**self._times(start),
                               "extendedProperties": {"private": {"clara_operation": event_id(key)}}}).json()
        return result["id"]

    def cancel_appointment(self, event):
        response = self._request("DELETE", self._path(event.doctor, event.id), headers={"If-Match": event.etag},
                                 params={"sendUpdates": "none"})
        return response.status_code == 204

    def close(self):
        self.client.close()
