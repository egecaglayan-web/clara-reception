import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def email_address(value):
    value = value.strip().casefold()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value):
        raise ValueError("Invalid email address.")
    return value


class Incoming(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str = Field(min_length=3, max_length=250, pattern=r"^[\x21-\x7e]+$")
    sender: str
    sender_name: str = Field(default="", max_length=100, pattern=r"^[^\r\n]*$")
    body: str = Field(min_length=1, max_length=12000)
    references: list[str] = Field(default_factory=list, max_length=30)
    authenticated: bool = False

    @field_validator("sender")
    @classmethod
    def validate_email(cls, value):
        return email_address(value)

    @field_validator("references")
    @classmethod
    def validate_references(cls, values):
        if any(not re.fullmatch(r"[\x21-\x7e]{3,250}", x) for x in values):
            raise ValueError("Invalid message reference.")
        return values


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["book", "reschedule", "cancel", "info", "human", "emergency", "clarify", "privacy"] = "clarify"
    language: Literal["tr", "en", "ar"] = "tr"
    doctor: Literal["ayse", "mehmet", "sara"] | None = None
    full_name: str | None = Field(default=None, max_length=100, pattern=r"^[^\r\n]*$")
    phone: str | None = Field(default=None, max_length=40, pattern=r"^[+0-9 ()-]*$")
    day: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    selection: int | None = Field(default=None, ge=1, le=3)
    appointment: int | None = Field(default=None, ge=1, le=30)
    confirmed: bool = False
    info: Literal["all", "hours", "address", "doctors"] = "all"


class Event(BaseModel):
    id: str
    doctor: str
    start: datetime
    end: datetime
    description: str = ""
    summary: str = ""
    etag: str = ""
    status: str = "confirmed"

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError("A time zone is required.")
        return value


class DeliveryReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["mark_sent", "retry"]
    confirmed: Literal[True]
