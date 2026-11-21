"""Load the 20 generated test dossiers (A01-A10, P01-P10) into the database as DRAFTS, without clicking through the app.

    python -m promoflow.batch_read A01 ...            (first) read every file with the app's local readers; saved in docs/generated_dossiers/_reads/
    python -m promoflow.batch_load users              create the 20 applicant accounts (safe to repeat: existing ones are skipped)
    python -m promoflow.batch_load load [A01 ...]     save the dossiers as drafts: every value is the TRUTH, the readers' answers are only compared with it
    python -m promoflow.batch_load report             the extraction-accuracy figures from the comparisons made while loading
    python -m promoflow.batch_load status [A01 ...]   who exists and what each draft holds
    python -m promoflow.batch_load reset [A01 ...]    delete the named batch accounts (default: all 20) with their cases and files

The accounts use the applicant's own email from the dossier (for example omar.sayegh@promoflow.test) and the development password
DEV_PASSWORD from .env, which is never printed. Nothing is submitted: every case stays a DRAFT. Only the 20 batch accounts are touched.

The 20 applicants come from docs/generated_dossiers/_expected/<code>.json (written by docs/dossier_gen_cs/dump_expected.py); these are fictional people.
Every entry goes through the section's own validated add() function, exactly like an entry typed or imported in the app."""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import func, select

from promoflow import config  # noqa: F401  (loads .env)
from promoflow import batch_read, batch_truth as bt
from promoflow.admin import AdminError, create_user
from promoflow.db.enums import CaseStatus, PromotionTrack, Rank, RoleName
from promoflow.db.models import CaseDocument, CourseTaught, PromotionCase, RankHistory, User
from promoflow.db.session import session_scope

ROOT = batch_read.ROOT
EXPECTED = ROOT / "_expected"
READS = batch_read.READS
CODES = [f"A{i:02d}" for i in range(1, 11)] + [f"P{i:02d}" for i in range(1, 11)]
TODAY = date.today()


def load_expected(code: str) -> dict:
    return json.loads((EXPECTED / f"{code}.json").read_text(encoding="utf-8"))


def all_expected(codes: list[str] | None = None) -> list[dict]:
    missing = [c for c in (codes or CODES) if not (EXPECTED / f"{c}.json").exists()]
    if missing:
        raise SystemExit(f"Missing expected-data files for {missing}. Run docs/dossier_gen_cs/dump_expected.py first.")
    return [load_expected(c) for c in (codes or CODES)]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---- accounts ---------------------------------------------------------------------------------------------------------------

def cmd_users(codes: list[str]) -> int:
    password = os.environ.get("DEV_PASSWORD", "")
    if len(password) < 10:
        print("DEV_PASSWORD is not set in .env (at least 10 characters). Nothing was created.")
        return 1
    created, skipped = [], []
    with session_scope() as s:
        for x in all_expected(codes):
            a = x["A"]
            if s.scalar(select(User).where(User.email == a["email"])) is not None:
                skipped.append(x["code"])
                continue
            try:
                u = create_user(s, email=a["email"], full_name=a["name"], college=a["college"], department=a["department"], password=password,
                                roles=[RoleName.APPLICANT])
            except AdminError as e:
                print(f"{x['code']}: {e}")
                return 1
            u.employee_id = a["employee_id"]
            u.profile_completed_at = datetime.now(timezone.utc)       # the person has "completed their profile", so login goes straight to the dossier
            created.append(x["code"])
    print(f"created {len(created)} account(s): {', '.join(created) or '-'}")
    print(f"already existed (left alone) {len(skipped)}: {', '.join(skipped) or '-'}")
    print("Password for all of them: the value of DEV_PASSWORD in .env (not printed).")
    return 0


# ---- the load -----------------------------------------------------------------------------------------------------------------

class Loader:
    def __init__(self, code: str):
        self.code = code
        self.x = load_expected(code)
        self.reads = batch_read.load_reads(code)
        self.files = batch_read.dossier_files(code)
        self.by_kind: dict[str, list] = {}
        for k, n, p in self.files:
            self.by_kind.setdefault(k, []).append((n, p))
        self.records: list[dict] = []             # one per compared field
        self.supplied: list[str] = []            # what had to be taken from the truth because the document does not show it
        self.steps: dict[str, str] = {}
        with session_scope() as s:
            self.uid = s.scalar(select(User.id).where(User.email == self.x["A"]["email"]))
        if self.uid is None:
            raise SystemExit(f"{code}: no account {self.x['A']['email']} (run: python -m promoflow.batch_load users)")

    # -- helpers
    def ctx(self, s):
        from promoflow.dossier.doc_entries import load_ctx
        return load_ctx(s, self.x["name"], self.uid)

    def rec(self, name):
        return self.reads.get(name) or {"items": [], "error": "not read", "route": None}

    def drafts(self, s, kind: str, key: str | None = None, only=None) -> list:
        """One draft per file (or per table row) of this kind: the reader's values, compared with the truth, the truth saved."""
        from promoflow.extraction.entry_docs import EntryDraft
        ctx = self.ctx(s)
        out = []
        for i, (name, path) in enumerate(self.by_kind.get(kind, [])):
            if only is not None and not only(name, i):
                continue
            rec = self.rec(name)
            items = rec["items"] or [None]
            data = path.read_bytes()
            for j, it in enumerate(items):
                idx = j if kind == "curriculum" else bt.truth_index(kind, name, i, self.x)
                if kind == "acceptance":
                    idx = int(name.rsplit("_", 1)[-1].split(".")[0]) - 1
                if idx is None or idx >= self._size(kind):
                    self.supplied.append(f"{name}: no matching item in the truth, skipped")
                    continue
                values = dict(it["values"]) if it else bt.blank_values(kind, ctx)
                truth = bt.BUILD[kind](self.x, idx)
                final, recs = bt.reconcile(kind, name, values, truth, found=it is not None)
                self.records += recs
                if kind == "paper" and self.x["papers"][idx][10] == "accepted":
                    continue                                           # an accepted paper is saved from its acceptance letter; this file is only scored
                key = final.pop("course_key", None)
                if kind in batch_read.COURSE_KINDS:
                    final["course_taught_id"] = self.course_id(key, final)
                out.append(EntryDraft(kind, name, data, final, [], rec.get("route") or "text"))
        return out

    def _size(self, kind: str) -> int:
        x = self.x
        return {"paper": len(x["papers"]), "acceptance": len(x["papers"]), "book": len(x["chapters"]), "conference": len(x["conferences"]),
                "award": len(x["award_docs"]), "peer_observation": len(x["peers"]), "curriculum": len(x["development"]), "innovation": len(x["innovations"]),
                "development": len(x["attended"]), "supervision": len(x["supervisions"]), "committee": len(x["committees"]), "admin": len(x["admin"]),
                "workshop": len(x["organised"]), "training": len(x["trainings"]), "community": len(x["community"]), "policy": len(x["policies"]),
                "position": len(x["nonacademic"]), "course_file": 10 ** 6}.get(kind, 10 ** 6)

    # the applicant's 6A courses, by key (filled once they are saved)
    courses: dict = {}

    def course_id(self, key, values):
        if key and key in self.courses:
            return self.courses[key]
        # not matched by the reader: use the first course taught in the semester that holds the item's date, else the first course
        d = values.get("observation_date") or values.get("activity_date")
        if isinstance(d, date):
            term = "fall" if (d.month >= 9 or d.month == 1) else "spring"
            start = d.year if d.month >= 9 else d.year - 1
            hit = next((v for k, v in self.courses.items() if k.startswith(f"{start}/{start + 1}|{term}|")), None)
            if hit:
                self.supplied.append("a course was taken from the date of the item (the reader did not match one)")
                return hit
        return next(iter(self.courses.values()), None)

    def add(self, kind_key: str, drafts: list, what: str = ""):
        from promoflow.dossier import doc_entries
        if not drafts:
            self.steps[what or kind_key] = "nothing to add"
            return
        with session_scope() as s:
            ctx = self.ctx(s)
            rep = doc_entries.add_entries(s, self.uid, kind_key, drafts, ctx)
        self.steps[what or kind_key] = f"added {rep.added}, already there {rep.skipped_existing}" + (f", REFUSED {len(rep.rejected)}: {rep.rejected[:3]}" if rep.rejected else "")
        log(f"{self.code} {what or kind_key}: {self.steps[what or kind_key]}")

    # -- the steps
    def section0(self):
        from promoflow.dossier import section0 as s0
        a = self.x["A"]
        phd = next(d for d in self.x["degrees"] if "philosophy" in d[0].lower())
        values = {"academic_year": a["academic_year"], "track": PromotionTrack.TO_ASSOCIATE if self.x["track"] == "associate" else PromotionTrack.TO_FULL,
                  "specialization": a["specialization"], "fine_specialization": a["fine_specialization"], "research_keywords": list(a["keywords"]),
                  "appointment_date": date.fromisoformat(a["appointment_date"]), "rank_on_appointment": Rank(bt.RANK[a["rank_on_appointment"].lower()]),
                  "current_rank_date": date.fromisoformat(a["current_rank_date"]), "scopus_author_id": a["scopus_id"], "orcid": a["orcid"],
                  "phd_outside_uae": phd[4] != "AE", "early_application": False, "exceptional_case": False, "exceptional_justification": None,
                  "previously_rejected": False, "rejection_date": None}
        with session_scope() as s:
            case_id = s0.save(s, self.uid, values, TODAY)
        self.steps["section 0"] = f"case {case_id}"
        log(f"{self.code} section 0 saved (case {case_id})")

    def section1(self):
        from promoflow.dossier import section1 as s1
        (name, path), = self.by_kind["application"]
        rec = self.rec(name)
        signed = (rec["items"][0]["values"].get("signed_date") if rec["items"] else None)
        self.records.append({"file": name, "kind": "application", "field": "signed_date", "reader": str(signed) if signed else None,
                             "truth": None, "result": "no truth" if signed else "missing"})
        signed = signed or date(2026, 11, 6)
        with session_scope() as s:
            s1.save(s, self.uid, {"decl_not_from_thesis": True, "decl_after_current_rank": True, "application_signed_date": signed}, TODAY,
                    (name, path.read_bytes()))
        self.steps["section 1"] = "saved"

    def ranks(self):
        from promoflow.dossier import section4 as s4
        self.add("rank", self.drafts_for("rank"), "rank decisions (with files)")
        with session_scope() as s:
            ctx = self.ctx(s)
            have = {(r.rank.value, r.held_from) for r in s.scalars(select(RankHistory).join(PromotionCase, PromotionCase.id == RankHistory.case_id).where(PromotionCase.applicant_id == self.uid))}
            added = skipped = 0
            for r in self.x["ranks"]:
                key = bt.RANK.get(r[0].lower())
                if key is None:
                    skipped += 1
                    continue
                v = {"rank": Rank(key), "date_obtained": date.fromisoformat(r[4]), "university": r[1], "country_code": r[3], "held_from": date.fromisoformat(r[4]),
                     "held_to": date.fromisoformat(r[5]) if r[5] else None, "at_this_university": "sharjah" in r[1].lower()}
                if (key, v["held_from"]) in have:
                    continue
                if s4.validate_rank(v, TODAY):
                    self.supplied.append(f"rank {r[0]} {r[4]}: refused {s4.validate_rank(v, TODAY)}")
                    continue
                s4.add_rank(s, self.uid, v, None)                       # the dossier has no document for this rank: only the CV lists it
                added += 1
        self.steps["ranks without a file"] = f"added {added}, not representable {skipped}"
        log(f"{self.code} ranks without a file: {self.steps['ranks without a file']}")

    def drafts_for(self, kind, **kw):
        with session_scope() as s:
            return self.drafts(s, kind, **kw)

    def papers(self):
        self.add("paper", self.drafts_for("paper"), "papers")
        self.add("acceptance", self.drafts_for("acceptance"), "accepted papers")

    def classification(self):
        from promoflow.dossier.section5 import classification as cl
        from promoflow.extraction import rule_reports
        (name, path), = self.by_kind["classform"]
        rec = self.reads.get(name) or {}
        used = {p[3] for p in self.x["papers"]}
        truth = [(self.x["journals"][k], bt.class_cell(self.x["journals"][k])) for k in sorted(used)]
        reader = {cl._norm(j["journal_name"]): j["classification"] for j in (rec.get("parsed") or {}).get("journals", [])}
        for j, cell in truth:
            r = reader.get(cl._norm(j["name"]))
            res = "missing" if r is None else ("match" if cl.form_class(r)[0] == j["cls"] else "wrong")
            self.records.append({"file": name, "kind": "classform", "field": "class", "reader": r, "truth": cell, "result": res})
        form = cl.ClassificationForm(journals=[cl.FormJournal(journal_name=j["name"], journal_name_arabic=None, classification=cell) for j, cell in truth])
        with session_scope() as s:
            case = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == self.uid))
            added = cl.declare_journals_from_form(s, case.id, form, 2026)
            cl.save_signed_form(s, case.id, self.uid, (name, path.read_bytes()))
        self.steps["journals classification form"] = f"{len(added)} journals declared"
        log(f"{self.code} classification form: {len(added)} journals declared")

    def courses_step(self):
        from promoflow.dossier.section6 import imports
        from promoflow.extraction.teaching_docs import CourseDraft, RegistrarReport, build_course_drafts, norm_code
        (name, path), = self.by_kind["registrar"]
        rec = self.reads.get(name) or {}
        reader = {}
        if rec.get("parsed"):
            for d in build_course_drafts(RegistrarReport(**rec["parsed"]))[0]:
                reader[(d.academic_year, d.semester, d.course_code)] = d
        truth_rows = []
        for r in self.x["schedule"]:
            key = (r["year"], r["semester"], norm_code(r["code"]))
            d = reader.get(key)
            for field, t, rv in (("students", r["students"], d.students if d else None), ("course_title", r["title"], d.course_title if d else None),
                                 ("crn", r["crn"], d.crn if d else None)):
                res = "missing" if rv is None else ("match" if bt.same(rv, t) else "wrong")
                self.records.append({"file": name, "kind": "registrar", "field": field, "reader": None if rv is None else str(rv), "truth": str(t), "result": res})
            truth_rows.append(CourseDraft(r["year"], r["semester"], norm_code(r["code"]), r["title"], r["level"], r["students"], r["crn"]))
        extra = len(set(reader) - {(d.academic_year, d.semester, d.course_code) for d in truth_rows})
        if extra:
            self.records.append({"file": name, "kind": "registrar", "field": "extra rows", "reader": str(extra), "truth": "0", "result": "wrong"})
        with session_scope() as s:
            rep = imports.add_courses(s, self.uid, truth_rows, (name, path.read_bytes()))
        self.steps["courses (6A)"] = f"added {rep.added}, already there {rep.skipped_existing}" + (f", REFUSED {rep.rejected[:3]}" if rep.rejected else "")
        log(f"{self.code} courses: {self.steps['courses (6A)']}")
        self.refresh_courses()

    def refresh_courses(self):
        with session_scope() as s:
            case = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == self.uid))
            self.courses = {batch_read.course_key(c): c.id for c in s.scalars(select(CourseTaught).where(CourseTaught.case_id == case.id).order_by(CourseTaught.id))}

    def satisfaction(self):
        from promoflow.dossier.section6 import imports
        from promoflow.extraction.teaching_docs import SatDraft, StudentEvaluations, build_sat_drafts, norm_code
        (name, path), = self.by_kind["evaluations"]
        rec = self.reads.get(name) or {}
        with session_scope() as s:
            case = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == self.uid))
            courses = list(s.scalars(select(CourseTaught).where(CourseTaught.case_id == case.id)))
            ns = [SimpleNamespace(id=c.id, academic_year=c.academic_year, semester=c.semester.value, course_code=c.course_code, students=c.students) for c in courses]
        reader = {}
        if rec.get("parsed"):
            for d in build_sat_drafts(StudentEvaluations(**rec["parsed"]), ns)[0]:
                reader[(d.academic_year, d.semester, d.course_code)] = d
        truth_rows = []
        for r in self.x["evals"]:
            key = (r["year"], r["semester"], norm_code(r["code"]))
            d = reader.get(key)
            for field, t, rv in (("respondents", r["respondents"], d.respondents if d else None), ("average_score", r["prof"], d.average_score if d else None)):
                res = "missing" if rv is None else ("match" if bt.same(rv, t) else "wrong")
                self.records.append({"file": name, "kind": "evaluations", "field": field, "reader": None if rv is None else str(rv), "truth": str(t), "result": res})
            cid = self.courses.get(f"{key[0]}|{key[1]}|{key[2]}")
            truth_rows.append(SatDraft(cid, f"{key[2]} - {r['label']}", key[0], key[1], key[2], r["students"], r["respondents"], r["prof"], 5.0))
        with session_scope() as s:
            rep = imports.add_satisfaction(s, self.uid, truth_rows, (name, path.read_bytes()))
        self.steps["student evaluations (6C)"] = f"added {rep.added}, already there {rep.skipped_existing}" + (f", REFUSED {rep.rejected[:3]}" if rep.rejected else "")
        log(f"{self.code} evaluations: {self.steps['student evaluations (6C)']}")

    def advising(self):
        from promoflow.dossier.section6 import imports
        from promoflow.extraction.teaching_docs import AdviseeList, build_advising_drafts
        items = []
        for name, path in self.by_kind["advisees"]:
            rec = self.reads.get(name) or {}
            if rec.get("parsed"):
                items.append((name, path.read_bytes(), AdviseeList(**rec["parsed"])))
        reader = build_advising_drafts(items)
        by_name = {d.filename: d for d in reader}
        names = [n for n, _ in self.by_kind["advisees"]]
        final = []
        for i, (name, path) in enumerate(self.by_kind["advisees"]):
            truth_n = self.x["advisees"][i] if i < len(self.x["advisees"]) else None
            d = by_name.get(name)
            rv = d.advisees if d else None
            res = "missing" if rv is None else ("match" if rv == truth_n else "wrong")
            self.records.append({"file": name, "kind": "advisees", "field": "advisees", "reader": None if rv is None else str(rv), "truth": str(truth_n), "result": res})
            if d is None:
                sem = f"{'Fall' if i % 2 == 0 else 'Spring'}"
                self.supplied.append(f"{name}: not read, skipped")
                continue
            d.advisees = truth_n
            for f in ("on_warning_at_start", "cleared_warning", "improved_gpa"):
                if getattr(d, f) is None:
                    setattr(d, f, 0)
            if d.meetings_held is None:
                d.meetings_held = 2
                self.supplied.append(f"{name}: number of meetings not on the list, set to 2")
            final.append(d)
        with session_scope() as s:
            rep = imports.add_advising(s, self.uid, final)
        self.steps["advising (6E)"] = f"added {rep.added}, already there {rep.skipped_existing}" + (f", REFUSED {rep.rejected[:3]}" if rep.rejected else "")
        log(f"{self.code} advising: {self.steps['advising (6E)']}")

    def run(self):
        t0 = time.time()
        self.section0()
        self.section1()
        self.add("cv", self.drafts_for("cv"), "section 2 (CV)")
        self.add("degree", self.drafts_for("degree"), "degrees")
        self.add("equivalency", self.drafts_for("equivalency"), "equivalency certificate")
        self.ranks()
        self.add("position", self.drafts_for("position"), "non-academic positions")
        self.papers()
        self.classification()
        for k, label in (("book", "book chapters"), ("conference", "conference papers"), ("funded", "funded project"), ("award", "awards"), ("scopus", "Scopus")):
            self.add(k, self.drafts_for(k), label)
        self.courses_step()
        self.add("peer_observation", self.drafts_for("peer_observation"), "peer observations")
        self.satisfaction()
        self.add("curriculum", self.drafts_for("curriculum"), "curriculum")
        self.advising()
        self.add("course_file", self.drafts_for("course_file"), "course files")
        self.add("innovation", self.drafts_for("innovation"), "teaching innovations")
        self.add("development", self.drafts_for("development"), "workshops attended")
        self.add("supervision", self.drafts_for("supervision"), "thesis supervision")
        for k, label in (("committee", "committees"), ("admin", "administrative positions"), ("workshop", "workshops organised"), ("training", "trainings"),
                         ("community", "community service"), ("policy", "policy contributions"), ("letter", "recommendation letter"),
                         ("conditions", "section 9 (conditions form)"), ("cover_letter", "section 10 (cover letter)")):
            self.add(k, self.drafts_for(k), label)
        out = {"code": self.code, "seconds": round(time.time() - t0), "steps": self.steps, "supplied": self.supplied, "records": self.records}
        (READS / f"{self.code}_load.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        log(f"{self.code} done in {out['seconds']}s: {len(self.records)} comparisons")


def cmd_load(codes: list[str]) -> int:
    for c in codes:
        missing = [n for k, n, p in batch_read.dossier_files(c) if n not in batch_read.load_reads(c)]
        if missing:
            print(f"{c}: {len(missing)} file(s) not read yet (run: python -m promoflow.batch_read {c}). Nothing loaded.")
            return 1
    for c in codes:
        Loader(c).run()
    return 0


# ---- report -----------------------------------------------------------------------------------------------------------------

def cmd_report(codes: list[str]) -> int:
    from collections import Counter, defaultdict
    tally: dict = defaultdict(Counter)
    for c in codes:
        p = READS / f"{c}_load.json"
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8"))["records"]:
            tally[(r["kind"], r["field"])][r["result"]] += 1
    if not tally:
        print("No comparisons yet: run `load` first.")
        return 1
    lines = ["| kind | field | compared | correct | wrong | missed | accuracy |", "|---|---|---|---|---|---|---|"]
    tot = Counter()
    for (kind, field), c in sorted(tally.items()):
        n = c["match"] + c["wrong"] + c["missing"]
        if not n:
            continue
        tot.update(c)
        lines.append(f"| {kind} | {field} | {n} | {c['match']} | {c['wrong']} | {c['missing']} | {c['match'] / n:.0%} |")
    n = tot["match"] + tot["wrong"] + tot["missing"]
    lines.append(f"| **all** | | {n} | {tot['match']} | {tot['wrong']} | {tot['missing']} | {tot['match'] / n:.1%} |")
    # reading time per file, from the seconds batch_read recorded for every file
    times: dict = defaultdict(list)
    for c in codes:
        for rec in batch_read.load_reads(c).values():
            times[(rec["kind"], rec.get("route") or "-")].append(rec["secs"])
    lines += ["", "Reading time per file (seconds; 'ocr' = scanned, 'text' = digital PDF):", "", "| kind | route | files | average | slowest | total |", "|---|---|---|---|---|---|"]
    allsecs = []
    for (kind, route), v in sorted(times.items()):
        allsecs += v
        lines.append(f"| {kind} | {route} | {len(v)} | {sum(v) / len(v):.1f} | {max(v):.1f} | {sum(v):.0f} |")
    for route in ("text", "ocr"):
        v = [s for (k, r), vs in times.items() if r == route for s in vs]
        if v:
            lines.append(f"| **all {route}** | | {len(v)} | {sum(v) / len(v):.1f} | {max(v):.1f} | {sum(v):.0f} |")
    lines.append(f"\nTotal reading time: {sum(allsecs) / 60:.0f} min for {len(allsecs)} files.")
    text = "\n".join(lines)
    (READS / "extraction_report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


# ---- status / reset -----------------------------------------------------------------------------------------------------------

def cmd_status(codes: list[str]) -> int:
    with session_scope() as s:
        for x in all_expected(codes):
            u = s.scalar(select(User).where(User.email == x["A"]["email"]))
            if u is None:
                print(f"{x['code']}  {x['A']['email']:<38} no account")
                continue
            case = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == u.id).order_by(PromotionCase.id.desc()))
            if case is None:
                print(f"{x['code']}  {x['A']['email']:<38} account {u.id}, no case")
                continue
            docs = s.scalar(select(func.count()).select_from(CaseDocument).where(CaseDocument.case_id == case.id))
            print(f"{x['code']}  {x['A']['email']:<38} account {u.id}, case {case.id} ({case.status.value}), {docs} documents")
    return 0


def cmd_reset(codes: list[str]) -> int:
    from sqlalchemy import delete
    from promoflow.db.models import AuditLogEntry, UserRole
    from promoflow.db.models.org import AuthSession
    with session_scope() as s:
        users = list(s.scalars(select(User).where(User.email.in_([x["A"]["email"] for x in all_expected(codes)]))))
        ids = [u.id for u in users]
        if not ids:
            print("nothing to reset")
            return 0
        case_ids = list(s.scalars(select(PromotionCase.id).where(PromotionCase.applicant_id.in_(ids))))
        s.execute(delete(AuditLogEntry).where(AuditLogEntry.user_id.in_(ids)))
        if case_ids:
            s.execute(delete(AuditLogEntry).where(AuditLogEntry.case_id.in_(case_ids)))
            s.execute(delete(PromotionCase).where(PromotionCase.id.in_(case_ids)))
        s.execute(delete(AuthSession).where(AuthSession.user_id.in_(ids)))
        s.execute(delete(UserRole).where(UserRole.user_id.in_(ids)))
        s.execute(delete(User).where(User.id.in_(ids)))
    print(f"deleted {len(ids)} account(s) and {len(case_ids)} case(s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m promoflow.batch_load", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["users", "load", "report", "status", "reset"])
    ap.add_argument("codes", nargs="*", help="limit to some applicants, e.g. A01 P03")
    args = ap.parse_args(argv)
    codes = [c.upper() for c in args.codes] or CODES
    return {"users": cmd_users, "load": cmd_load, "report": cmd_report, "status": cmd_status, "reset": cmd_reset}[args.command](codes)


if __name__ == "__main__":
    sys.exit(main())
