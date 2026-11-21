"""More scanned documents read by plain rules on the OCR text (or the text layer): degree certificates, rank decisions, awards, thesis
supervision records, teaching innovation reports and policy documents. Same idea and same contract as rule_letters.py: each function returns a
dict with the keys of the matching schema in entry_docs_more.py / entry_docs.py, None for anything not found, and nothing is guessed. This module
registers itself in rule_letters.RULES / REQUIRED when it is imported (rule_letters does that at its end).
"""
import re

from promoflow.extraction import rule_letters as RL
from promoflow.extraction.rule_letters import DATE, _clean, _date, _flat, _junk, _lines, _titlecase

def _fix(text: str) -> str:
    """OCR slips that change meaning: "Al-assisted" for "AI-assisted", "2oth" for "20th", "loT" for "IoT"."""
    text = re.sub(r"\bloT\b", "IoT", text)
    text = re.sub(r"\bAl(?=[- ](?:assisted|powered|based|driven|enabled|tools?|coding|writing))", "AI", text)
    return re.sub(r"(?<=\d)[oO](?=(?:th|st|nd|rd)\b)", "0", text)


# ---- degree certificate ---------------------------------------------------------------------------------------------

def degree_cert(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    lines = _lines(text)
    m = re.search(r"the degree of (.+?)(?: in | Thesis:| Conferred on)(.+?)?(?= Thesis:| Conferred on|$)", flat)
    name = _clean(m.group(1)) if m else None
    subject = _clean(m.group(2)) if m and m.group(2) else None
    thesis = re.search(r"Thesis:\s*(.+?)\s+Conferred on", flat)
    when = re.search(rf"Conferred on ({DATE})", flat)
    uni = country = None
    for i, line in enumerate(lines):
        if re.match(r"certificate of\b", line, re.I):
            above = [x for x in lines[:i] if not _junk(x)]
            if above and len(above[-1].split()) <= 3 and len(above) >= 2:
                country, uni = above[-1], above[-2]
            elif above:
                uni = above[-1]
            break
    return {"degree_name": name, "field_of_study": subject, "university": _titlecase(uni), "country": _clean(country),
            "conferral_date": _date(when.group(1)) if when else None, "thesis_title": _clean(thesis.group(1)) if thesis else None}


# ---- rank decision --------------------------------------------------------------------------------------------------

def rank_decision(text: str, applicant: str = "") -> dict:
    flat = _fix(_flat(text))
    m = re.search(r"academic rank of (.+?) at (.+?),? in the", flat)
    effective = re.search(rf"with effect from ({DATE})", flat, re.I)
    decided = re.search(rf"\bDate:\s*({DATE})", flat)
    inst = _clean(m.group(2)) if m else None
    country = None
    for line in [x for x in _lines(text)[:6] if not _junk(x)][:4]:
        if inst and line.casefold() == inst.casefold():
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z ]{2,30}", line) and len(line.split()) <= 3 and not re.search(
                r"university|human|faculty|decision|resources|affairs|office", line, re.I):
            country = line
            break
    return {"rank_title": _clean(m.group(1)) if m else None, "institution": inst, "country": country,
            "effective_date": _date(effective.group(1)) if effective else None, "decision_date": _date(decided.group(1)) if decided else None}


# ---- award ----------------------------------------------------------------------------------------------------------

_ORG = r"UNIVERSITY|COLLEGE|DEPARTMENT|ASSOCIATION|FORUM|JOURNAL|CONFERENCE|COUNCIL|SOCIETY|INSTITUTE|CENTRE|CENTER|ACADEMY|SCHOOL|FACULTY|OFFICE"


def award_doc(text: str, applicant: str = "") -> dict:
    lines = [x for x in _lines(_fix(text)) if not _junk(x)]
    flat = " ".join(lines)
    idx = next((i for i, x in enumerate(lines) if re.search(r"is proudly presented|is hereby awarded|awarded to|presented to", x, re.I)), None)
    name = body = None
    if idx is not None:
        above = lines[:idx]
        end = next((i for i in range(len(above) - 1, -1, -1) if re.search(r"\b(?:award|prize|medal|honou?r|fellowship)\s*$", above[i], re.I)), None)
        if end is not None:
            start, words = end, len(above[end].split())
            while words < 3 and start > 0:                    # a name is at least three words ("Young Researcher Award"); the line above completes it
                start -= 1
                words += len(above[start].split())
            name = _titlecase(" ".join(above[start:end + 1]))
            body = _titlecase(" ".join(above[:start]))
    when = re.search(rf"Awarded on (?:the )?({DATE})", flat, re.I)
    ctx = re.search(r"(?:in recognition of|for the paper|for)\s+(.+?)\s*(?:Awarded on|$)", " ".join(lines[idx + 1:]) if idx is not None else "", re.I)
    return {"award_name": name, "awarding_body": body, "award_date": _date(when.group(1)) if when else None,
            "context": _clean(ctx.group(0)) if ctx else None}


# ---- thesis supervision (the defence decision form, and the proposal approval form) -----------------------------------

def supervision_doc(text: str, applicant: str = "") -> dict:
    lines = _lines(_fix(text))
    flat = _flat(_fix(text))
    last = (applicant or "").replace(".", " ").split()[-1].casefold() if (applicant or "").strip() else ""
    student = thesis = degree = role = began = defence = conferral = outcome = None

    if re.search(r"candidate", flat, re.I) and re.search(r"programme", flat, re.I):                # defence decision (form GS-7)
        i = next((n for n, x in enumerate(lines) if x.upper() == "PROGRAMME"), None)
        if i is not None and i + 2 < len(lines):
            student, degree = _clean(lines[i + 1]), _clean(lines[i + 2])
        dates = re.findall(rf"\b\d{{1,2}}/\d{{1,2}}/\d{{4}}\b|{DATE}", flat[flat.upper().find("STUDIES BEGAN"):] if "STUDIES BEGAN" in flat.upper() else flat)
        numeric = [d for d in dates if "/" in d]
        longer = [d for d in dates if "/" not in d]
        defence = numeric[0] if numeric else None
        began = _date(longer[0]) if longer else None
        t = re.search(r"THESIS TITLE\s+(.+?)\s+Examination committee", flat, re.I)
        thesis = _clean(t.group(1)) if t else None
        o = re.search(r"decided:\s*(.+?)\.\s", flat + " ", re.I)
        outcome = _clean(o.group(1)) if o else None
        c = re.search(rf"graduation ceremony \(({DATE})\)", flat, re.I)
        conferral = _date(c.group(1)) if c else None
        if last:
            for n, x in enumerate(lines):
                if last in x.casefold() and n + 2 < len(lines) and re.search(r"supervis|chair|examin|member", lines[n + 2], re.I):
                    role = _clean(lines[n + 2])
                    break
    else:                                                                                          # proposal approval (form GS-3)
        s = re.search(r"STUDENT\s+(.+?)\s*\(ID", flat)
        student = _clean(s.group(1)) if s else None
        p = re.search(r"PROGRAMME\s+(.+?)\s+SUPERVISOR", flat)
        degree = _clean(p.group(1)) if p else None
        t = re.search(r"WORKING TITLE\s+(.+?)\s+The Graduate", flat)
        thesis = _clean(t.group(1)) if t else None
        sup = re.search(r"SUPERVISOR\s+(.+?)\s+PROPOSAL", flat)
        if sup and (not last or last in sup.group(1).casefold()):
            role = "Supervisor"
        b = re.search(rf"Studies began on ({DATE}|\d{{1,2}}/\d{{1,2}}/\d{{4}})", flat, re.I)
        began = _date(b.group(1)) if b else None
    return {"student_name": student, "thesis_title": thesis, "degree": degree, "applicant_role": role, "studies_began": began,
            "defence_date": defence, "conferral_date": conferral, "outcome": outcome}


# ---- teaching innovation report -----------------------------------------------------------------------------------------

_SECTION_HEADS = ("what was done", "method", "implementation", "summary", "background", "measured outcome", "findings", "results", "reflection",
                  "next steps", "indicator", "measure", "outcome", "conclusion")


def innovation_doc(text: str, applicant: str = "") -> dict:
    lines = _lines(_fix(text))
    flat = " ".join(lines)
    title = None
    for i, line in enumerate(lines):
        if re.search(r"teaching innovation report", line, re.I) and i + 1 < len(lines):
            title = _clean(lines[i + 1])
            break
    course = re.search(r"\b([A-Z]{2,5}\s?\d{3}),\s*((?:Fall|Spring|Summer)\s*\d{4})", flat)
    # The report's sections, by heading line: each heading owns the text up to the next heading.
    sections, current = {}, None
    for line in lines:
        head = line.strip().lower().rstrip(":")
        if head in _SECTION_HEADS:
            current = head
            sections.setdefault(current, [])
        elif current and not re.match(r"(?:OFFICIAL|STAMP|SIMULATED)", line):
            sections[current].append(line)
    def section(*names):
        for n in names:
            if sections.get(n):
                return _clean(" ".join(sections[n]))
        return None
    return {"title": title, "course_code": _clean(course.group(1)) if course else None, "term": _clean(course.group(2)) if course else None,
            "what_was_done": section("what was done", "method", "implementation"), "measured_outcome": section("measured outcome", "findings", "results", "outcome")}


# ---- policy document ----------------------------------------------------------------------------------------------------

def policy_doc(text: str, applicant: str = "") -> dict:
    lines = _lines(text)
    flat = _flat(text)
    name = None
    for i, line in enumerate(lines):
        if re.search(r"(?:^|\s)policy document$", line, re.I) and i + 1 < len(lines):      # "Policy document" alone, or after the university's name
            name = _clean(lines[i + 1])
            break
    body = re.search(r"Approved by:\s*([^|]+?)\s*(?:\||Effective|$)", flat)
    eff = re.search(rf"Effective:\s*({DATE})", flat)
    last = (applicant or "").replace(".", " ").split()[-1].casefold() if (applicant or "").strip() else ""
    role = None
    role_words = r"member|chair|secretary|coordinator|reviewer|drafting|lead"
    if last:
        for n, x in enumerate(lines):
            pos = x.casefold().find(last)
            if pos < 0:
                continue
            after = x[pos + len(last):]                                  # the role on the same line as the name (a text PDF) ...
            if re.search(role_words, after, re.I):
                role = _clean(after)
            elif n + 1 < len(lines) and re.search(role_words, lines[n + 1], re.I):      # ... or on the next line (a scan, read column by column)
                role = _clean(lines[n + 1])
            if role:
                break
    return {"policy_name": name, "approving_body": _clean(body.group(1)) if body else None,
            "effective_date": _date(eff.group(1)) if eff else None, "applicant_role": role}


RULES = {"degree": degree_cert, "rank": rank_decision, "award": award_doc, "supervision": supervision_doc, "innovation": innovation_doc,
         "policy": policy_doc}
REQUIRED = {"degree": ("degree_name", "conferral_date"), "rank": ("rank_title", "effective_date"), "award": ("award_name", "award_date"),
            "supervision": ("student_name", "thesis_title"), "innovation": ("title",), "policy": ("policy_name", "effective_date")}
# These rules need to know who the applicant is (to find THEIR row in a committee list or an examiner table).
NEEDS_APPLICANT = RL.NEEDS_APPLICANT
NEEDS_APPLICANT.update({"supervision", "policy"})

RL.RULES.update(RULES)
RL.REQUIRED.update(REQUIRED)
