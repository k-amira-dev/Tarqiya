"""Does the assistant report the gap that really exists?

For some of the 20 generated dossiers (all complete), remove ONE known item inside a database transaction, ask the assistant's tools what is
missing, and check that exactly that section is reported (and that the written answer names it). Every trial is ROLLED BACK: nothing is ever
committed, so the stored dossiers are not changed. Run:

    python -m promoflow.assistant.eval_gaps            baseline on all 20, trials on six of them
    python -m promoflow.assistant.eval_gaps A01 P05    trials on the dossiers named

Writes docs/supervisor_report/assistant_eval.json.
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from promoflow.assistant import chat, tools
from promoflow.db import session as db_session
from promoflow.db.enums import DocumentKind
from promoflow.db.models import (
    CaseDocument, CommitteeMembership, Degree, Publication, PromotionCase, RankHistory, ScopusEvidence, User,
)
from promoflow.dossier import section9, section10
from promoflow.dossier.section6 import courses as courses_mod

ROOT = Path(__file__).resolve().parents[2] / "docs" / "generated_dossiers"
OUT = Path(__file__).resolve().parents[2] / "docs" / "supervisor_report" / "assistant_eval.json"
DEFAULT_TRIALS = ["A01", "A05", "A10", "P01", "P05", "P10"]


def _docs(case_id, section, kind, slot=None):
    cond = [CaseDocument.case_id == case_id, CaseDocument.section_code == section, CaseDocument.kind == kind, CaseDocument.entity_table.is_(None)]
    if slot is not None:
        cond.append(CaseDocument.slot == slot)
    return delete(CaseDocument).where(*cond)


# name, the section expected to be reported, and what to remove
def trials(case_id: int):
    return [
        ("no degrees", "3", lambda s: s.execute(delete(Degree).where(Degree.case_id == case_id))),
        ("no CV file", "2", lambda s: s.execute(_docs(case_id, "2", DocumentKind.CV))),
        ("no signed application form", "1", lambda s: s.execute(_docs(case_id, "1", DocumentKind.SIGNED_FORM))),
        ("no rank history", "4", lambda s: s.execute(delete(RankHistory).where(RankHistory.case_id == case_id))),
        ("no Scopus evidence", "5", lambda s: s.execute(delete(ScopusEvidence).where(ScopusEvidence.case_id == case_id))),
        ("no registrar report", "6", lambda s: s.execute(_docs(case_id, "6A", DocumentKind.EVIDENCE, courses_mod.REPORT_SLOT))),
        ("no committee membership", "7", lambda s: s.execute(delete(CommitteeMembership).where(CommitteeMembership.case_id == case_id))),
        ("no signed conditions form", "9", lambda s: s.execute(_docs(case_id, "9", DocumentKind.SIGNED_FORM, section9.FORM_SLOT))),
        ("no signed cover letter", "10", lambda s: s.execute(_docs(case_id, "10", DocumentKind.SIGNED_FORM, section10.LETTER_SLOT))),
        ("no paper marked for promotion", "5", lambda s: s.execute(update(Publication).where(Publication.case_id == case_id).values(submit_for_promotion=False))),
    ]


def _sections_reported(status: dict) -> set[str]:
    return {g["section"] for g in status["gaps"] if g["kind"] == "section"}


def run(codes: list[str], log=print) -> dict:
    today = date.today()
    out = {"date": today.isoformat(), "baseline": [], "trials": []}
    people = {}
    for f in sorted((ROOT / "_expected").glob("[AP]??.json")):
        x = json.loads(f.read_text(encoding="utf-8"))
        people[x["code"]] = x["A"]["email"]
    with Session(db_session.engine) as s:
        try:
            uid = {c: s.scalar(select(User.id).where(User.email == e)) for c, e in people.items()}
            cid = {c: s.scalar(select(PromotionCase.id).where(PromotionCase.applicant_id == u).order_by(PromotionCase.id.desc())) for c, u in uid.items()}
            for code in sorted(people):                                              # baseline: a complete dossier should report no missing section
                st = tools.dossier_status(s, uid[code], today)
                out["baseline"].append({"case": code, "completed": st["completed"], "total": st["total"], "sections_reported": sorted(_sections_reported(st))})
            log(f"baseline: {sum(1 for b in out['baseline'] if not b['sections_reported'])} of {len(out['baseline'])} dossiers report no missing section")
            for code in codes:
                for name, expected, remove in trials(cid[code]):
                    t0 = time.time()
                    s.begin_nested()                                                 # a savepoint: undone below, whatever happens
                    try:
                        remove(s)
                        s.flush()
                        s.expire_all()
                        status = tools.dossier_status(s, uid[code], today)
                        facts = {"status": status, "requirements": {"track": None, "thresholds": [], "scoring_forms": []}, "today": today.isoformat(), "glossary": []}
                        answer = chat.reply("What is missing from my application?", facts, llm=None).text
                    finally:
                        s.rollback()
                    reported = _sections_reported(status)
                    out["trials"].append({"case": code, "removed": name, "expected": expected, "reported": sorted(reported),
                                          "detected": expected in reported, "exact": reported == {expected} or (name.startswith("no paper") and expected in reported),
                                          "named_in_answer": f"Section {expected}" in answer, "research_gap_shown": any(g["kind"] == "research" for g in status["gaps"]),
                                          "seconds": round(time.time() - t0, 1)})
                    log(f"{code} {name}: expected {expected}, reported {sorted(reported)}")
        finally:
            s.rollback()
    T = out["trials"]
    out["summary"] = {"trials": len(T), "detected": sum(t["detected"] for t in T), "exact": sum(t["exact"] for t in T),
                      "named_in_answer": sum(t["named_in_answer"] for t in T),
                      "baseline_clean": sum(1 for b in out["baseline"] if not b["sections_reported"]), "baseline": len(out["baseline"])}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = run([c.upper() for c in sys.argv[1:]] or DEFAULT_TRIALS, log=lambda m: print(m, flush=True))
    print(json.dumps(res["summary"]))
