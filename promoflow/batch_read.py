"""Step 1 of the batch load: run the app's own LOCAL readers (no model, no tokens) over every file of a generated dossier and keep what they
returned, so the slow part (OCR) is done once and the result can be compared with the truth and loaded as often as needed.

    python -m promoflow.batch_read A01 A02 ...        read the files of these dossiers (a file already read is not read again)

The result of one dossier is docs/generated_dossiers/_reads/<code>.json: for each file the kind it was read as, the route (text layer or OCR),
the seconds it took, and what the reader returned (values and the notes the app would show the applicant)."""
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "docs" / "generated_dossiers"
READS = ROOT / "_reads"

# (file name prefix, how it is read). Files not listed here are not read by the app (the .docx copy of the application form, the website
# screenshots of the journals, the community summary); they are not loaded either.
FILEMAP = [
    ("01_signed_application_form", "application"), ("02_cv", "cv"), ("03_degree", "degree"), ("04_equivalency", "equivalency"), ("05_rank", "rank"),
    ("06_employment", "position"), ("07_paper", "paper"), ("08_acceptance", "acceptance"), ("10_book", "book"), ("11_conference", "conference"),
    ("12_funded", "funded"), ("13_journals_classification_form", "classform"), ("14_scopus", "scopus"), ("16_award", "award"),
    ("17_registrar", "registrar"), ("18_peer", "peer_observation"), ("19_student_evaluation", "evaluations"), ("20_curriculum", "curriculum"),
    ("21_advising", "advisees"), ("22_syllabus", "course_file"), ("23_teaching_innovation", "innovation"), ("24_supervision", "supervision"),
    ("25_attendance", "development"), ("26_committee", "committee"), ("27_admin", "admin"), ("28_workshop", "workshop"), ("29_training", "training"),
    ("30_policy", "policy"), ("31_community_proof", "community"), ("32_recommendation", "letter"), ("33_conditions", "conditions"),
    ("34_signed_cover", "cover_letter"),
]
ORDER = {kind: i for i, (_, kind) in enumerate(FILEMAP)}


def kind_of(filename: str) -> str | None:
    return next((kind for prefix, kind in FILEMAP if filename.startswith(prefix)), None)


def natural(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def dossier_folder(code: str) -> Path:
    return next(ROOT.glob(f"{code}_*"))


def dossier_files(code: str) -> list[tuple[str, str, Path]]:
    """[(kind, file name, path)] for the files the app reads, in natural order inside each kind."""
    out = []
    for f in dossier_folder(code).iterdir():
        k = kind_of(f.name)
        if f.is_file() and k:
            out.append((k, f.name, f))
    return sorted(out, key=lambda t: (ORDER[t[0]], natural(t[1])))


# ---- JSON with dates ----------------------------------------------------------------------------------------------------

def enc(v):
    if isinstance(v, date):
        return {"__date__": v.isoformat()}
    if isinstance(v, dict):
        return {k: enc(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [enc(x) for x in v]
    return v


def dec(v):
    if isinstance(v, dict):
        if set(v) == {"__date__"}:
            return date.fromisoformat(v["__date__"])
        return {k: dec(x) for k, x in v.items()}
    if isinstance(v, list):
        return [dec(x) for x in v]
    return v


def load_reads(code: str) -> dict:
    p = READS / f"{code}.json"
    return dec(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else {}


def save_reads(code: str, reads: dict) -> None:
    READS.mkdir(parents=True, exist_ok=True)
    tmp = READS / f"{code}.json.tmp"
    tmp.write_text(json.dumps(enc(reads), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(READS / f"{code}.json")


# ---- reading ------------------------------------------------------------------------------------------------------------

COURSE_KINDS = {"peer_observation", "innovation", "course_file"}      # their draft points at one of the applicant's 6A courses


def course_key(c) -> str:
    return f"{c.academic_year}|{getattr(c.semester, 'value', c.semester)}|{c.course_code}"


def _read_one(kind: str, name: str, data: bytes, ctx) -> dict:
    from promoflow.extraction import local_read, rule_reports
    from promoflow.extraction.entry_docs import KINDS, read_entries

    t0 = time.time()
    rec = {"kind": kind, "route": None, "items": [], "error": None}
    try:
        if kind == "registrar":
            parsed = rule_reports.registrar(data)
            rec["route"], rec["parsed"] = "text", parsed.model_dump() if parsed else None
        elif kind == "evaluations":
            parsed = rule_reports.evaluations(data)
            rec["route"], rec["parsed"] = "text", parsed.model_dump() if parsed else None
        elif kind == "advisees":
            parsed = rule_reports.advisees(data)
            rec["route"], rec["parsed"] = "text", parsed.model_dump() if parsed else None
        elif kind == "classform":
            parsed = rule_reports.classification_form(data)
            rec["route"], rec["parsed"] = "text", parsed.model_dump() if parsed else None
        else:
            drafts = read_entries(KINDS["cover_letter" if kind == "application" else kind], name, data, ctx)
            rec["route"] = drafts[0].route if drafts else None
            rec["items"] = [{"values": d.values, "issues": d.issues} for d in drafts]
    except Exception as e:                                           # a file that cannot be read is a result, not a crash
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    rec["secs"] = round(time.time() - t0, 1)
    return rec


def read_dossier(code: str, log=print) -> dict:
    from promoflow.db.session import session_scope
    from promoflow.dossier.doc_entries import load_ctx

    x = json.loads((ROOT / "_expected" / f"{code}.json").read_text(encoding="utf-8"))
    reads = load_reads(code)
    with session_scope() as s:
        ctx = load_ctx(s, x["name"])
    files = dossier_files(code)
    # Peer observations, innovations and syllabi point at a course of 6A: in the app the applicant has entered 6A first (from the registrar
    # report), so the reader is given the courses THE REGISTRAR REPORT READ gave, and the answer is stored as the course's key.
    reg_name = next((n for k, n, _ in files if k == "registrar"), None)
    for kind, name, path in files:
        if name in reads:
            continue
        if kind in COURSE_KINDS and ctx.courses == [] and reg_name:
            reg = reads.get(reg_name, {}).get("parsed")
            if reg:
                from promoflow.extraction.teaching_docs import RegistrarReport, build_course_drafts
                drafts, _ = build_course_drafts(RegistrarReport(**reg))
                ctx.courses = [SimpleNamespace(id=i + 1, course_code=d.course_code, academic_year=d.academic_year, semester=d.semester, role="instructor",
                                               students=d.students) for i, d in enumerate(drafts)]
        rec = _read_one(kind, name, path.read_bytes(), ctx)
        if kind in COURSE_KINDS:
            by_id = {c.id: course_key(c) for c in ctx.courses}
            for it in rec["items"]:
                if "course_taught_id" in it["values"]:
                    it["values"]["course_key"] = by_id.get(it["values"]["course_taught_id"])
                    it["values"]["course_taught_id"] = None
        reads[name] = rec
        log(f"{code} {name}  [{kind}] {rec['route'] or '-'} {rec['secs']}s" + (f"  ERROR {rec['error']}" if rec["error"] else ""))
        if len(reads) % 10 == 0:
            save_reads(code, reads)
    save_reads(code, reads)
    return reads


def main(argv=None) -> int:
    codes = [c.upper() for c in (argv if argv is not None else sys.argv[1:])]
    if not codes:
        print(__doc__)
        return 1
    for code in codes:
        t0 = time.time()
        reads = read_dossier(code, log=lambda m: print(m, flush=True))
        print(f"== {code}: {len(reads)} files read in {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
