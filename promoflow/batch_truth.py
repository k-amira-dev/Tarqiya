"""The truth for a generated dossier (docs/generated_dossiers/_expected/<code>.json), turned into the same keys the app's readers return, and the
comparison between the two.

For every file the loader asks three things of a truth builder:
    compare   fields the document PRINTS: the reader's value is compared with the truth (match / wrong / missing) and the truth is what gets saved.
    fill      fields the app works out itself (level, scope, type codes) or the document does not show: the truth is used only when the reader found nothing.
    force     fields the document cannot show (study period, the full date when only a year is printed): the truth is saved, and nothing is scored.
Only `compare` fields count in the extraction-accuracy figures."""
import hashlib
import re
from datetime import date

from promoflow.extraction.entry_docs import KINDS


def D(s):
    return date.fromisoformat(s) if s else None


def _norm(v):
    if isinstance(v, str):
        t = re.sub(r"\b(dr|prof|professor|mr|mrs|ms)\b\.?", " ", v.lower())
        return re.sub(r"[^a-z0-9]+", " ", t).strip()
    return v


def same(reader, truth) -> bool:
    if isinstance(truth, (int, float)) and not isinstance(truth, bool) and isinstance(reader, (int, float)) and not isinstance(reader, bool):
        return abs(float(reader) - float(truth)) < 0.006
    if isinstance(truth, list):
        return isinstance(reader, list) and [_norm(a) for a in reader] == [_norm(a) for a in truth]
    return _norm(reader) == _norm(truth)


def blank_values(kind: str, ctx) -> dict:
    """What the app's builder returns for a document that gave nothing at all (a file that could not be read)."""
    schema = KINDS[kind].schema
    empty = {n: ([] if "list" in str(f.annotation) else None) for n, f in schema.model_fields.items()}
    return KINDS[kind].build(schema.model_validate(empty), ctx)[0]


# ---- small mappers ------------------------------------------------------------------------------------------------------

def lvl(text: str | None):
    t = (text or "").lower()
    return "department" if "department" in t else "college" if ("college" in t or "faculty" in t) else "university" if "universit" in t else None


def issn_for(j: dict) -> str:
    """The generated journals have no ISSN, and the app needs one: a fixed, valid-looking number (starting with 9) is made from the journal's name,
    publisher and class, so the same journal always gets the same one. It is NOT a real ISSN."""
    h = int(hashlib.sha256(f"{j['name']}|{j['publisher']}|{j['cls']}".encode()).hexdigest()[:8], 16)
    digits = f"{9000000 + h % 1000000:07d}"
    total = sum(w * int(c) for w, c in zip(range(8, 1, -1), digits))
    check = (11 - total % 11) % 11
    return f"{digits[:4]}-{digits[4:]}{'X' if check == 10 else check}"


def class_cell(j: dict) -> str:
    """The text the signed Journals Classification Form prints in its class column for this journal."""
    if j["cls"] == "A":
        return "Q1" if j.get("q") == "Q1" else "A"
    return f"{j['q']}-B" if j.get("q") else "B"


def valid_isbn(printed: str) -> str:
    """The generated ISBN is a placeholder (978-0-0000-0000-0) whose check digit is wrong, so the app refuses it. The same number with the correct
    last digit is used instead; it is still not a real book."""
    digits = re.sub(r"\D", "", re.sub(r"\(.*?\)", "", printed))[:12]
    check = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits)) % 10) % 10
    return f"{digits[:3]}-{digits[3]}-{digits[4:8]}-{digits[8:12]}-{check}"


def money(text: str | None):
    m = re.search(r"([A-Z]{3})\s*([\d,\.]+)", text or "")
    return (float(m.group(2).replace(",", "")), m.group(1)) if m else (None, None)


RANK = {"assistant lecturer": "assistant_lecturer", "post-doctoral researcher": "postdoc", "lecturer": "lecturer", "assistant professor": "assistant_professor", "associate professor": "associate_professor", "professor": "professor"}
REPRESENTABLE = set(RANK)                                  # Section 4 keeps four ranks; "Assistant Lecturer" and "Post-Doctoral Researcher" cannot be entered


def _paper_pos(x: dict, authors: list[str]):
    last = x["A"]["last"].lower()
    return next((k for k, a in enumerate(authors, 1) if a.split()[-1].lower() == last), None)


# ---- builders: (compare, fill, force) -----------------------------------------------------------------------------------

def t_degree(x, i):
    d = x["degrees"][i]
    name = d[0].lower()
    level = "phd" if "philosophy" in name else "master" if "master" in name else "bachelor" if "bachelor" in name else "other_doctorate"
    return ({"level": level, "specialization": d[1], "university": d[2], "country_code": d[4], "graduation_date": D(d[7]), "thesis_title": d[8]}, {},
            {"study_from": D(d[5]), "study_to": D(d[6])})


def t_equivalency(x, i):
    d = next(g for g in x["degrees"] if "philosophy" in g[0].lower())
    return {"award_date": D(d[7])}, {"qualification": f"{d[0]} in {d[1]}", "institution": f"{d[2]}, {d[3]}"}, {}


def t_rank(x, i):
    r = x["ranks_evidenced"][i]
    return ({"rank": RANK.get(r[0].lower()), "university": r[1], "country_code": r[3], "date_obtained": D(r[4]), "held_from": D(r[4])},
            {"at_this_university": "sharjah" in r[1].lower()}, {"held_to": D(r[5])})


def t_position(x, i):
    p = x["nonacademic"][i]
    return {"position": p[0], "employer": p[1], "country_code": p[3], "date_from": D(p[4]), "date_to": D(p[5])}, {}, {}


def t_paper(x, i):
    n, title, doi, jkey, vol, iss, pages, year, dt, role, status, lang, authors = x["papers"][i]
    j = x["journals"][jkey]
    pos = _paper_pos(x, authors)
    base = {"title": title, "journal_name": j["name"], "author_position": pos, "total_authors": len(authors)}
    force = {"_authors": list(authors), "_other_authors": [a for k, a in enumerate(authors, 1) if k != pos], "issn": issn_for(j)}
    fill = {"issue": "1", "publisher": j["publisher"], "doi": doi, "main_author_basis": ("first_author" if pos == 1 else "corresponding_author") if role == "main" else None}
    if status == "accepted":
        return base, fill, {**force, "applicant_role": role}
    return ({**base, "publisher": j["publisher"], "volume": vol, "issue": iss or None, "pages": pages, "language": lang, "applicant_role": role},
            fill, {**force, "issue_date": D(dt), "status": "published"})


def t_acceptance(x, i):
    n, title, doi, jkey, vol, iss, pages, year, dt, role, status, lang, authors = x["papers"][i]
    j = x["journals"][jkey]
    pos = _paper_pos(x, authors)
    return ({"title": title, "journal_name": j["name"], "acceptance_date": D(dt), "author_position": pos, "total_authors": len(authors)},
            {"publisher": j["publisher"], "main_author_basis": ("first_author" if pos == 1 else "corresponding_author") if role == "main" else None},
            {"_authors": list(authors), "_other_authors": [a for k, a in enumerate(authors, 1) if k != pos], "issn": issn_for(j), "applicant_role": role,
             "status": "accepted", "issue_date": None, "volume": None, "issue": None, "pages": None})


def t_book(x, i):
    c = x["chapters"][i]
    return ({"book_title": c["book"], "chapter_title": c["title"], "publisher": c["publisher"], "publication_date": D(c["date"]),
             "main_or_sole_author": c["role"] in ("sole", "main")}, {}, {"isbn": valid_isbn(c["isbn"])})


def t_conference(x, i):
    c = x["conferences"][i]
    return ({"title": c["title"], "conference_title": c["conf"], "organizer": c["organizer"], "place": c["place"], "conference_date": D(c["date"]),
             "pages": c["pages"], "main_or_sole_author": c["role"] in ("sole", "main")}, {}, {"scopus_indexed": False})


def t_funded(x, i):
    p = x["project"]
    amount, cur = money(p["amount"])
    ftype = p["funder_type"].lower()
    code = "internal" if "internal" in ftype else "government" if "government" in ftype else "company" if ("company" in ftype or "industry" in ftype) else \
        "international" if "international" in ftype else "university"
    return ({"title": p["title"], "funding_body": p["funder"], "amount": amount, "currency": cur, "start_date": D(p["start"]), "end_date": D(p["end"]),
             "role": "pi" if "principal" in p["role"].lower() else "ci", "status": p["status"].lower()}, {"funder_code": code}, {})


def t_award(x, i):
    a = x["award_docs"][i]
    scope = "institutional" if lvl(a["by"]) or "sharjah" in a["by"].lower() else None
    return {"name": a["name"], "awarding_body": a["by"], "year": a["year"]}, {"scope_code": scope or "regional"}, {}


def t_scopus(x, i):
    a = x["A"]
    return {"h_index": a["scopus_h"], "total_citations": a["scopus_citations"], "screenshot_date": D(a["scopus_date"])}, {}, {}


def t_peer(x, i):
    p = x["peers"][i]
    role = p["observer_role"].lower()
    code = "hod" if ("head" in role or "chair" in role) else "tl_centre" if ("teaching" in role or "centre" in role or "center" in role) else "peer"
    return ({"observer_name": p["observer"], "observation_date": D(p["date"]), "rating": p["overall"]}, {"observer_code": code, "scale_max": 5.0}, {})


def t_curriculum(x, i):
    d = x["development"][i]
    title = f"{d['code']} {d['title']}"
    typ = d["type"].lower()
    kind = "new_course" if "new" in typ else "modified_course" if ("modif" in typ or "existing" in typ) else "study_plan" if "study plan" in typ else "program"
    return ({"course_or_program": title, "approval_date": D(d["approved"]), "type_code": kind, "approved_by": lvl(d["approved_by"])},
            {"description": d["summary"][:2000]}, {})


def t_course_file(x, i):
    return {}, {"kept_in_code": "blackboard"}, {}


def t_innovation(x, i):
    v = x["innovations"][i]
    code = {"ai": "ai_tool"}.get(v["kind"], v["kind"])
    return {"type_code": code}, {"description": f"{v['title']}", "measured_outcome": v["outcome"]}, {}


def t_development(x, i):
    a = x["attended"][i]
    return {"title": a[0], "activity_date": D(a[1]), "organizer": a[2], "hours": float(a[3])}, {}, {}


def t_supervision(x, i):
    s = x["supervisions"][i]
    deg = s["degree"].lower()
    role = s["role"].lower()
    return ({"student_name": s["student"], "thesis_title": s["title"], "start_date": D(s["start"]), "degree": "phd" if ("phil" in deg or "doctor" in deg) else "msc",
             "role": "associate" if ("co" in role or "associate" in role) else "main"},
            {"status": "graduated" if s.get("defence") else "in_progress", "graduation_date": D(s.get("defence"))}, {})


def t_committee(x, i):
    c = x["committees"][i]
    sig = c[5].lower()
    level = lvl(c[0]) or ("department" if "head" in sig else "college" if "dean" in sig else "university")
    return {"committee_name": c[0], "role_code": c[1].lower(), "date_from": D(c[2]), "date_to": D(c[3])}, {"level": level}, {}


def t_admin(x, i):
    a = x["admin"][i]
    title = a[0]
    t = title.lower()
    code = ("other" if "deputy" in t else "hod" if "head of department" in t else "vice_dean" if ("vice dean" in t or "assistant dean" in t) else
            "dean" if "dean" in t else "program_coordinator" if "coordinator" in t else "unit_director" if "director" in t else "other")
    unit = title.split(",", 1)[1].strip() if "," in title else title
    return {"unit": unit, "date_from": D(a[1]), "date_to": D(a[2])}, {"position_code": code}, {}


def t_workshop(x, i):
    w = x["organised"][i]
    role = w[1].lower()
    return ({"title": w[0], "role": "organiser_and_lecturer" if ("and" in role) else "organiser" if "organis" in role else "lecturer", "activity_date": D(w[2]),
             "attendees": w[4]}, {"organized_by": lvl(w[3]) or "university"}, {})


def t_training(x, i):
    t = x["trainings"][i]
    return ({"title": t[0], "host_organisation": t[1], "hours": float(t[2]), "activity_date": D(t[3])}, {"inside_university": "sharjah" in t[1].lower()}, {})


def t_community(x, i):
    c = x["community"][i]
    typ = c[0].lower()
    code = "public_lecture" if "lecture" in typ else "volunteering" if "volunteer" in typ else "other"
    return ({"title": c[1], "applicant_role": c[2], "date_from": D(c[3]), "date_to": D(c[4]), "beneficiary_organisation": c[5], "deliverables": c[6]},
            {"activity_type_code": code}, {})


def t_policy(x, i):
    p = x["policies"][i]
    role = p["role"].lower()
    return ({"policy_name": p["name"], "activity_date": D(p["approved"]), "role_code": "chaired" if "chair" in role else "reviewed" if "review" in role else "drafted"},
            {"level": lvl(p["body"]) or "department"}, {})


def t_letter(x, i):
    r = x["recommender"]
    return {"writer_name": r["name"], "writer_rank": r["title"], "writer_institution": r["org"]}, {"relationship_code": "colleague"}, {}


def t_signed(x, i):
    return {}, {"signed_date": date(2026, 11, 6)}, {}


BUILD = {"degree": t_degree, "equivalency": t_equivalency, "rank": t_rank, "position": t_position, "paper": t_paper, "acceptance": t_acceptance, "book": t_book,
         "conference": t_conference, "funded": t_funded, "award": t_award, "scopus": t_scopus, "peer_observation": t_peer, "curriculum": t_curriculum,
         "course_file": t_course_file, "innovation": t_innovation, "development": t_development, "supervision": t_supervision, "committee": t_committee,
         "admin": t_admin, "workshop": t_workshop, "training": t_training, "community": t_community, "policy": t_policy, "letter": t_letter,
         "cv": t_signed, "conditions": t_signed, "cover_letter": t_signed, "application": t_signed}


def truth_index(kind: str, name: str, i: int, x: dict) -> int | None:
    """Which truth item a file is about: the file's place among the files of its kind (they are numbered in the order of the truth), except degrees and
    ranks, which are named after what they certify."""
    if kind == "degree":
        tok = name.lower()
        want = "bachelor" if "bsc" in tok else "master" if "msc" in tok else "philosophy"
        return next((k for k, d in enumerate(x["degrees"]) if want in d[0].lower()), None)
    if kind == "rank":
        tok = re.sub(r"^05_rank_evidence_|(_scan)?\.pdf$", "", name.lower())
        return next((k for k, r in enumerate(x["ranks_evidenced"]) if r[0].lower().replace(" ", "_") == tok), None)
    if kind in ("equivalency", "scopus", "funded", "letter", "cv", "conditions", "cover_letter", "application"):
        return 0
    return i


def reconcile(kind: str, name: str, values: dict, truth: tuple, found: bool) -> tuple[dict, list[dict]]:
    """Apply a truth builder's result to what the reader returned. Returns (final values, one record per compared field)."""
    compare, fill, force = truth
    out, records = dict(values), []
    for k, t in compare.items():
        r = values.get(k)
        if t is None and r in (None, ""):
            continue
        if not found or r in (None, ""):
            res = "missing"
        else:
            res = "match" if same(r, t) else "wrong"
        records.append({"file": name, "kind": kind, "field": k, "reader": None if res == "missing" else str(r), "truth": str(t), "result": res})
        if t is not None:
            out[k] = t
    for k, t in fill.items():
        if out.get(k) in (None, "") and t is not None:
            out[k] = t
    for k, t in force.items():
        out[k] = t
    return out, records
