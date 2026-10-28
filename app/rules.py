import re
import unicodedata
from datetime import datetime, time, timedelta


def folded(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold().replace("ı", "i"))
                   if not unicodedata.combining(c))


def language(text):
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"\b(merhaba|randevu|istiyorum|iptal|tesekkur|saat|evet|onayliyorum|adim|secenek|lutfen)\b", folded(text)):
        return "tr"
    return "en"


def safety(text):
    t = folded(text)
    if re.search(r"\b(?:chest\s+pain|difficulty\s+breathing|severe\s+bleeding|suicid|kill\s+myself|"
                 r"gogus\s+agr|nefes\s+alam|siddetli\s+kanama|intihar|kendimi\s+oldur|"
                 r"(?:ال)?(?:الم\s+الصدر|صعوبة\s+التنفس|نزيف\s+شديد|انتحار))\w*", t):
        return "emergency"
    if re.search(r"\b(?:another\s+patient|someone\s+else|baska\s+hasta|baskasinin|(?:ال)?(?:زوجي|مريض\s+اخر))\w*", t):
        return "privacy"
    # Keep fee/cost whole-word forms; suffix matching would include feel/costume.
    # Arabic stems match folded input: نتائج becomes نتايج after normalization.
    if re.search(r"\b(?:prescription|test\s+result|medication|insurance|billing|complaint|human|"
                 r"payment|price|angry|terrible\s+service|symptom|real\s+person|speak\s+to\s+someone|"
                 r"recete|tahlil|ilac|sigorta|fatura|sikayet|insan|dokuntu|ucret|odeme|"
                 r"(?:ال)?(?:وصفة|نتايج|دواء|تامين|شكوى|موظف))\w*|\b(?:costs?|fees?)\b", t):
        return "human"
    return None


def owned(event, sender):
    addresses = [line.partition(":")[2].strip().casefold()
                 for line in event.description.splitlines()
                 if line.partition(":")[0].strip() == "patient_email"]
    return addresses == [sender.casefold()]


def eligible(start, now, zone):
    if start.utcoffset() is None or now.utcoffset() is None:
        return False
    s, n = start.astimezone(zone), now.astimezone(zone)
    return (1 <= (s.date() - n.date()).days <= 30 and s.weekday() < 5
            and s.second == 0 and s.microsecond == 0 and s.minute in (0, 30)
            and (time(9) <= s.time() <= time(11, 30) or time(13) <= s.time() <= time(16, 30)))


def candidates(now, zone, day=None):
    first = datetime.combine(now.astimezone(zone).date() + timedelta(days=1), time(), zone)
    if day:
        first = datetime.combine(datetime.strptime(day, "%Y-%m-%d").date(), time(), zone)
        days = [first]
    else:
        days, cursor = [], first
        while len(days) < 3:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
    result = []
    for date in days:
        for minute in range(9 * 60, 17 * 60, 30):
            slot = date + timedelta(minutes=minute)
            if eligible(slot, now, zone):
                result.append(slot)
    return result


def exact_choice(body):
    """Pre-write code gate: an explicit time or numbered option plus an affirmative choice."""
    t = folded(body)
    if (any(x in t for x in ("not ", "don't", "do not", "degil", "istemiyorum", "hayir", "etmeyin", "yapmayin"))
            or re.search(r"\biptal etme(?:yin|yiniz)?\b", t)
            or re.search(r"(?:^|\s)(?:no|لا)(?:\s|$)", t) or "?" in t or "؟" in t):
        return False
    return bool(re.search(r"\b(please|book|choose|yes|confirm|istiyorum|seciyorum|lutfen|onayliyorum|evet)\b|نعم|احجز|اختار|اوافق|أوافق", t))


def cancellation_confirmed(body, *, confirmation_target_id=None, target_id=None):
    if not target_id or confirmation_target_id != target_id:
        return False
    t = folded(body)
    return exact_choice(body) and bool(re.search(r"cancel|iptal|إلغاء|الغاء|نعم|\byes\b|\bevet\b|onayliyorum", t))
