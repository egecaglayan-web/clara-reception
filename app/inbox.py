import imaplib
import re
import ssl
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

from app.models import Incoming


QUOTE_SEPARATOR = re.compile(
    r"^[ \t]*>"
    r"|^[ \t]*On[ \t]+[^\n]*(?:\n[ \t]*[^\n]*)?wrote:[ \t]*$"
    r"|^[ \t]*[^\n]*<[^<>\n]+>[ \t]+adresine[ \t]+sahip[ \t]+kullanıcı[^\n]*"
    r"(?:\n[ \t]*[^\n]*)?tarihinde[ \t]+şunu[ \t]+yazdı:[ \t]*$"
    r"|^[ \t]*-{2,}[ \t]*Original Message[ \t]*-{2,}",
    re.MULTILINE | re.IGNORECASE,
)


def parse_email(raw, max_body_chars=12000):
    if len(raw) > 131072:
        raise ValueError("Email exceeds the size limit.")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if message.defects:
        raise ValueError("Invalid email format.")
    auto = str(message.get("Auto-Submitted", "no")).lower()
    if (auto != "no" or message.get("List-ID") or message.get("Precedence", "").lower() in ("bulk", "list", "junk")
            or message.get_content_type() == "multipart/report" or message.get("Return-Path") == "<>"):
        return None
    if len(message.get_all("From", [])) != 1 or len(message.get_all("Message-ID", [])) != 1:
        raise ValueError("Exactly one sender and message ID are required.")
    addresses = getaddresses([str(message["From"])])
    if len(addresses) != 1:
        raise ValueError("Multiple senders are not accepted.")
    name, sender = addresses[0]
    # Only Gmail's first Authentication-Results header is trusted; the body and later headers are not.
    auth = str(message.get_all("Authentication-Results", [""])[0])
    domain = sender.rpartition("@")[2].lower()
    authenticated = bool(re.match(r"\s*mx\.google\.com\s*;", auth, re.I)
                         and re.search(r"(?:^|[;\s])dmarc=pass\b[^;]*\bheader\.from=" + re.escape(domain) + r"(?:[;\s]|$)", auth, re.I))
    part = message.get_body(preferencelist=("plain",))
    if part is None:
        raise ValueError("This version requires a plain-text email part.")
    body = part.get_content()
    if len(body) > max_body_chars:
        raise ValueError("Email text exceeds the limit.")
    # Quoted earlier correspondence must never be read again as a confirmation or request.
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = QUOTE_SEPARATOR.split(body, maxsplit=1)[0].strip()
    references = re.findall(r"<[^<>\s]{1,248}>", str(message.get("References", "")) + " " + str(message.get("In-Reply-To", "")))
    return Incoming(message_id=str(message["Message-ID"]).strip(), sender=sender, sender_name=name,
                    body=body, references=references[-30:], authenticated=authenticated)


class DemoInbox:
    def __init__(self):
        self.pending = []

    def add(self, message):
        self.pending.append((message.message_id, message))

    def read(self):
        return list(self.pending)

    def mark(self, uid):
        self.pending = [(key, value) for key, value in self.pending if key != uid]

    def close(self):
        pass


class GmailInbox:
    def __init__(self, config):
        self.config = config
        self.connection = None

    def connect(self, readonly=False):
        self.close()
        connection = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port,
                                      ssl_context=ssl.create_default_context(), timeout=self.config.timeout_seconds)
        self.connection = connection
        connection.login(self.config.gmail_address, self.config.gmail_app_password)
        status, _ = connection.select(self.config.imap_folder, readonly=readonly)
        if status != "OK":
            raise RuntimeError("Could not open the IMAP folder.")
        return connection

    def read(self):
        connection = self.connect()
        status, data = connection.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("IMAP search failed.")
        result = []
        for uid in data[0].split()[:self.config.batch_size]:
            status, sizes = connection.uid("fetch", uid, "(RFC822.SIZE)")
            size = re.search(rb"RFC822.SIZE (\d+)", b" ".join(x for x in sizes if isinstance(x, bytes)))
            if status != "OK" or size is None:
                raise RuntimeError("Could not read the IMAP message size.")
            if int(size[1]) > 131072:
                result.append((uid, ValueError("Email size limit.")))
                continue
            status, parts = connection.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                raise RuntimeError("Could not read the IMAP message.")
            raw = next((x[1] for x in parts if isinstance(x, tuple)), None)
            try:
                if raw is None:
                    raise ValueError("Empty IMAP message.")
                parsed = parse_email(raw, self.config.max_body_chars)
            except (ValueError, TypeError, UnicodeError, LookupError):
                parsed = ValueError("Message could not be parsed safely; review it in the mailbox.")
            result.append((uid, parsed))
        return result

    def mark(self, uid):
        status, _ = self.connection.uid("store", uid, "+FLAGS", "(\\Seen)")
        if status != "OK":
            raise RuntimeError("IMAP flagging failed.")

    def close(self):
        if self.connection:
            try:
                self.connection.logout()
            except (OSError, imaplib.IMAP4.error):
                pass
            self.connection = None
