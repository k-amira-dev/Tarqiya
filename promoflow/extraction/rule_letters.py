"""Read the fixed-wording scanned letters and certificates with plain rules (regular expressions) on the OCR text: no model, no tokens, and
the document text never leaves the machine.

Each function takes the OCR text of one page and returns a dict with the SAME keys as the matching schema in entry_docs.py (so it can stand in
for the model's answer), with None for anything it could not find. Nothing is guessed: a field the rules do not find is None, and
`missing()` tells the caller which required fields are None so it can ask the applicant instead of calling a model.

The wording these rules know is what these letters say today ("appointed as X of the Y, from D to D", "attended the workshop entitled",
"serving as ... in"). A letter worded differently simply gives None for the fields it does not match.
"""
import re

_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
# OCR sometimes drops the space between a day, a month and a year ("01September 2020to"), so spaces inside a date are optional.
DATE = rf"(?:\d{{1,2}}(?:st|nd|rd|th)?(?:\s*of)?\s*{_MONTH}\.?\s*\d{{4}}|{_MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s*\d{{4}}|{_MONTH}\.?\s*\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}})"
_STAMP = re.compile(r"(simulated|official|stamp|seal)\b", re.I)


def _flat(text: str) -> str:
    """The text on one line (a sentence that wraps in the scan is one sentence again). A day the OCR read as "o8" becomes "08"."""
    flat = " ".join(text.split())
    return re.sub(rf"(?<![A-Za-z0-9])[oO](\d)(?=\s*{_MONTH})", lambda m: "0" + m.group(1), flat)


def _date(value: str | None) -> str | None:
    """A date with its spaces put back ("31August 2023" -> "31 August 2023"), so the date reader in entry_docs.py understands it."""
    if not value:
        return None
    value = re.sub(r"\b([A-Za-z]{3,4})\.(?=\s*\d)", r"\1", value)                       # "Jun. 14, 2022" -> "Jun 14, 2022"
    us = re.fullmatch(r"\s*([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})\s*", value)
    if us:                                                                              # "Jun 14, 2022" -> "14 Jun 2022"
        return f"{us.group(2)} {us.group(1)} {us.group(3)}"
    return " ".join(re.sub(r"(?<=\d)(?=(?!(?:st|nd|rd|th)\b)[A-Za-z])|(?<=[A-Za-z])(?=\d)", " ", value).split())


def _clean(value: str | None) -> str | None:
    value = (value or "").strip(" ,;:.\"“”'")
    return " ".join(value.split()) or None


def _quoted(flat: str) -> str | None:
    m = re.search(r'["“”]\s*(.+?)\s*["“”]', flat)
    return _clean(m.group(1)) if m else None


def _heading(text: str) -> str | None:
    """The organisation printed ABOVE the certificate's heading ("CERTIFICATE OF ...", "LETTER OF ..."), joined if it wraps."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for i, line in enumerate(lines):
        if re.match(r"(?:certificate|letter) of\b", line, re.I):
            return _clean(" ".join(lines[:i])) if lines[:i] else None
    return None


def _period(flat: str, start_word: str = "from") -> tuple[str | None, str | None]:
    """(start, end) from "between A and B" / "from A to B" / "from A until further notice". Spaces around the words are optional (OCR drops them)."""
    m = re.search(rf"between\s+({DATE})\s*and\s*({DATE})", flat, re.I)       # tried first: "between A and B" also starts like "between A"
    if m:
        return _date(m.group(1)), _date(m.group(2))
    m = re.search(rf"(?<![A-Za-z]){start_word}\s*({DATE})(?:\s*(?:to|until|through)\s*({DATE}|further\s*notice))?", flat, re.I)
    if m:
        end = m.group(2)
        return _date(m.group(1)), (None if not end or end.lower().replace(" ", "") == "furthernotice" else _date(end))
    return None, None


def _signer_title(text: str) -> str | None:
    """The signer's job title: the last line that starts like one ("Dean, College of ...", "Head, Department of ...")."""
    found = [x.strip() for x in text.splitlines()
             if re.match(r"(?:Dean|Head|Chair|Director|Vice|Provost|Rector|Chancellor|President|Coordinator)\b", x.strip())]
    return _clean(found[-1]) if found else None


# ---- one function per kind (same keys as the schemas in entry_docs.py) ---------------------------------------------------

def committee_letter(text: str) -> dict:
    flat = _flat(text)
    m = re.search(r"appointed as (?:the )?(?P<role>.+?) (?:of|to|in|on) the (?P<name>.+?),?\s+(?:from|for the period)", flat, re.I)
    start, end = _period(flat)
    return {"committee_name": _clean(m.group("name")) if m else None, "role": _clean(m.group("role")) if m else None,
            "date_from": start, "date_to": end, "signer_title": _signer_title(text)}


def admin_letter(text: str) -> dict:
    flat = _flat(text)
    m = re.search(r"(?:is|been|are)\s+(?:assigned|appointed|designated)\s+as\s+(?:the\s+)?(?P<pos>.+?),?\s+(?:from|with effect from)\s", flat, re.I)
    start, end = _period(flat)
    return {"position_title": _clean(m.group("pos")) if m else None, "unit": None, "date_from": start, "date_to": end}


def workshop_cert(text: str) -> dict:
    flat = _flat(text)
    role = re.search(r"(?:acted|served|participated) as (?:the )?(.+?) (?:of|in|for) the (?:workshop|event|seminar|conference)", flat, re.I)
    when = re.search(rf"held\s*on\s*({DATE})", flat, re.I)
    count = re.search(r"(?:with|attended by)\s+(\d+)\s+participants", flat, re.I)
    return {"title": _quoted(flat), "organized_by": _heading(text), "role": _clean(role.group(1)) if role else None,
            "activity_date": _date(when.group(1)) if when else None, "attendees": int(count.group(1)) if count else None}


def training_cert(text: str) -> dict:
    flat = _flat(text)
    hours = re.search(r"(\d+(?:\.\d+)?)[- ]hours?\b", flat, re.I)
    when = re.search(rf"\bon\s*({DATE})", flat, re.I)
    return {"title": _quoted(flat), "host_organisation": _heading(text), "hours": float(hours.group(1)) if hours else None,
            "activity_date": _date(when.group(1)) if when else None}


def attendance_cert(text: str) -> dict:
    flat = _flat(text)
    hours = re.search(r"(\d+(?:\.\d+)?)\s+(?:training\s+)?hours", flat, re.I)
    when = re.search(rf"held\s*on\s*({DATE})", flat, re.I)
    kind = re.search(r"attended the (workshop|seminar|conference|course|webinar|symposium)", flat, re.I)
    return {"title": _quoted(flat), "organiser": _heading(text), "activity_date": _date(when.group(1)) if when else None,
            "hours": float(hours.group(1)) if hours else None, "event_type": kind.group(1).lower() if kind else None}


def community_letter(text: str) -> dict:
    flat = _flat(text)
    role = re.search(r"(?:for )?(?:serving|acting|working|volunteering) as (?:a |an |the )?(.+?) in\b", flat, re.I)
    start, end = _period(flat, "between")
    if start is None:                                              # a single month: the date line right after the quoted title
        m = re.search(rf'["“”]\s*\.?\s*(?:in |on )?({DATE})\.', flat)
        start = end = _date(m.group(1)) if m else None
        if start is None:
            m = re.search(rf"\b({_MONTH}\.? \d{{4}})\s*\.", flat)
            start = end = _date(m.group(1)) if m else None
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    outputs = None
    for i, line in enumerate(lines):
        if re.search(rf"{DATE}\.?$", line) and i + 1 < len(lines) and not _STAMP.search(lines[i + 1]) \
                and not re.match(r"(director|dean|head)", lines[i + 1], re.I):
            outputs = _clean(lines[i + 1])
            break
    return {"organisation": _heading(text), "activity_title": _quoted(flat), "role": _clean(role.group(1)) if role else None,
            "date_from": start, "date_to": end, "outputs": outputs}


RULES = {"committee": committee_letter, "admin": admin_letter, "workshop": workshop_cert, "training": training_cert,
         "attendance": attendance_cert, "community": community_letter}

# What a draft cannot do without: if one of these is None the caller must not pretend the document was read.
REQUIRED = {"committee": ("committee_name", "role", "date_from"), "admin": ("position_title", "date_from"),
            "workshop": ("title", "activity_date"), "training": ("title", "activity_date"),
            "attendance": ("title", "activity_date"), "community": ("activity_title", "date_from")}


def missing(kind: str, fields: dict) -> list[str]:
    """The required fields the rules did not find (empty list = the document was read)."""
    return [k for k in REQUIRED[kind] if not fields.get(k)]

# ---- helpers shared with rule_docs.py and rule_text.py (defined here so the import order of the three modules never matters) ----------

# The kinds whose rules need to know who the applicant is (to find THEIR row in a list); the modules add their kinds here.
NEEDS_APPLICANT: set[str] = set()

_SMALL = {"of", "and", "for", "the", "in", "on", "at", "to", "de", "al"}


def _titlecase(text: str | None) -> str | None:
    """"NORTHFIELD INSTITUTE OF TECHNOLOGY" -> "Northfield Institute of Technology" (only when the text is printed in capitals)."""
    text = _clean(text)
    if not text or not text.isupper():
        return text
    text = re.sub(r"\b(AND|OF|FOR)(?=[A-Z]{4,}\b)", r"\1 ", text)           # the OCR sometimes glues a small word to the next one ("ANDSECURITY")
    out = []
    for i, w in enumerate(text.split()):
        if w.startswith("(") or any(ch.isdigit() for ch in w):                # an acronym in brackets or a year stays as printed
            out.append(w)
        else:
            out.append(w.lower() if (i and w.lower() in _SMALL) else w.lower().capitalize())
    return " ".join(out)


def _lines(text: str) -> list[str]:
    return [x.strip() for x in text.splitlines() if x.strip()]


def _junk(line: str) -> bool:
    """The "SIMULATED - FOR TESTING" watermark and similar, however the OCR or the text layer spaced it."""
    return re.sub(r"[^A-Za-z]", "", line).upper().startswith(("SIMULATED", "OFFICIAL", "STAMP", "SEAL"))


from promoflow.extraction import rule_docs  # noqa: E402,F401  (registers the document rules in RULES and REQUIRED; must come after the definitions above)
from promoflow.extraction import rule_text  # noqa: E402,F401  (registers the text-document rules too)
