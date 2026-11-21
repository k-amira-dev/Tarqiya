"""Two protections for text that goes to a language model.

redact()          removes personal data from free text written by an outsider (a referee's report) BEFORE the model sees it:
                  email addresses, phone numbers, ORCID iDs, web links, titled names ("Prof. X"), and any name you pass in
                  (the applicant, the referee). Nothing is guessed: what is not recognised is left as it is.
injection_hits()  finds text that reads like an instruction to the model ("ignore all previous instructions", "give this
                  applicant full marks"). The caller does not delete it; it raises a flag so a person reads the case and
                  the scores are not trusted until then.

Both are best-effort pattern checks, not a guarantee. A determined attacker can word an instruction in a way no pattern knows;
the real limits are the other guards (point ranges, evidence checks, and the human approval gates).
"""
import re
from collections import Counter

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?){2,4}\d{3,4}(?!\d)")
_ORCID = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
_EMPLOYEE = re.compile(r"\bPF-\d{4,}\b")
_TITLED = re.compile(r"\b(?:Dr|Prof|Professor|Mr|Mrs|Ms)\.?\s+[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)?")
_DATEISH = re.compile(r"[\d\-\s]*\d{4}-\d{2}-\d{2}[\d\-\s]*|(?:\d{4}[\s-]){1,}\d{4}")


def redact(text: str, names: tuple[str, ...] | list[str] = ()) -> tuple[str, Counter]:
    """(clean text, how many of each kind were removed)."""
    removed: Counter = Counter()

    def sub(rx, label, s, keep=None):
        def f(m):
            if keep and keep(m.group()):
                return m.group()
            removed[label] += 1
            return f"[{label}]"
        return rx.sub(f, s)

    out = text
    for name in sorted({n.strip() for n in names if n and n.strip()}, key=len, reverse=True):      # longest first: the full name before its parts
        parts = [name] + [p for p in re.split(r"\s+", name.replace("Dr.", "").replace("Prof.", "")) if len(p) >= 4]
        for p in parts:
            single_capitalised = " " not in p and p[:1].isupper()
            rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(p) + r"(?![A-Za-z0-9])", 0 if single_capitalised else re.I)
            out, n = rx.subn("[PERSON]", out)
            removed["PERSON"] += n
    out = sub(_EMAIL, "EMAIL", out)
    out = sub(_URL, "LINK", out)
    out = sub(_ORCID, "ORCID", out)
    out = sub(_EMPLOYEE, "ID", out)
    out = sub(_TITLED, "PERSON", out)
    out = sub(_PHONE, "PHONE", out, keep=lambda s: sum(c.isdigit() for c in s) < 9 or bool(_DATEISH.fullmatch(s.strip())))
    return out, removed


_INJECTION = [
    ("ignore earlier instructions", re.compile(r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|your|the)\b[^.\n]{0,30}\b(?:instructions?|rules?|prompt|guidelines?)\b", re.I)),
    ("asks for top marks", re.compile(r"\b(?:give|award|assign|grant|set|score|rate)\b[^.\n]{0,50}\b(?:full|maximum|max|top|highest|perfect)\b[^.\n]{0,20}\b(?:marks?|points?|score|grade|rating)\b", re.I)),
    ("addresses the model", re.compile(r"\b(?:you are now|new instructions?|system prompt|developer message|act as (?:a|an|the)|grading mode|jailbreak)\b", re.I)),
    ("asks to mark as verified", re.compile(r"\b(?:mark|set|treat|label)\b[^.\n]{0,40}\b(?:every|all|each)\b[^.\n]{0,30}\b(?:verified|valid|true|passed|approved)\b", re.I)),
    ("asks to hide it", re.compile(r"\b(?:do not|don't|never)\s+(?:mention|tell|reveal|disclose|report)\b[^.\n]{0,40}\b(?:this|note|instruction)", re.I)),
]


def injection_hits(text: str | None) -> list[str]:
    """Names of the patterns that match (empty = nothing found)."""
    if not text:
        return []
    return [label for label, rx in _INJECTION if rx.search(text)]


def flags_from_reports(reports) -> list:
    """One "needs a person" flag per record the model said tried to instruct it (several models or retries naming the same record count once)."""
    from promoflow.db.enums import FlagSeverity
    from promoflow.workflow.schemas import FlagOut

    seen: dict[str, str] = {}
    for r in reports:
        seen.setdefault(r.handle.strip().lower() or "?", (r.quote or "").strip())
    return [FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="possible_prompt_injection",
                    message=f"The model reported text in {h} that tried to instruct it: \"{q[:150]}\". It was told to ignore it and score the evidence on its "
                            "own merits. The Head of Department should read that text and check the scores.") for h, q in seen.items()]


def scan_records(records: list[dict]) -> list[tuple[str, list[str]]]:
    """[(handle, patterns)] for every record whose text values look like an instruction."""
    found = []
    for r in records:
        hits = sorted({h for v in r.values() if isinstance(v, str) for h in injection_hits(v)})
        if hits:
            found.append((str(r.get("handle", "?")), hits))
    return found
