"""Read-only facts for the applicant assistant.

Every number here comes from code the application already runs (the Review & Submit checklist, the eligibility rules, the policy
thresholds and scoring forms in the database). Nothing here writes to the database, and nothing here contains a name, an email or the
text of any document: only counts, labels and statuses, so it is safe to hand to a language model.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus, PromotionTrack
from promoflow.db.models import PromotionCase, PromotionCriteria, Rubric
from promoflow.dossier import section11
from promoflow.dossier.section0 import EDITABLE, active_case, current_policy
from promoflow.rules.research import CLASS_A_MIN_PERCENTILE

# Section code -> the page's url path (the same values as SECTIONS in ui/shell.py; a test keeps them equal).
SECTION_PATHS = {
    "0": "applicant-details", "1": "application-form", "2": "curriculum-vitae", "3": "degrees", "4": "ranks", "5": "research",
    "6": "teaching", "7": "service", "8": "recommendation-letters", "9": "conditions-form", "10": "cover-letter", "11": "review-submit",
}

TRACK_LABEL = {PromotionTrack.TO_ASSOCIATE: "Assistant Professor to Associate Professor",
               PromotionTrack.TO_FULL: "Associate Professor to Professor"}

# (field on the criteria row, label shown to the applicant, group)
CRITERIA_FIELDS = [
    ("min_years_in_rank", "Minimum years in the current rank", "Eligibility"),
    ("min_years_at_institution", "Minimum years at the university", "Eligibility"),
    ("early_application_months", "Months an early application may be submitted before eligibility", "Eligibility"),
    ("exceptional_min_years", "Minimum years for an exceptional case", "Eligibility"),
    ("reapply_min_years", "Years to wait before applying again after a rejection", "Eligibility"),
    ("min_total_publications", "Minimum total publications", "Research"),
    ("min_sole_main_author", "Minimum papers as sole or main author", "Research"),
    ("min_published", "Minimum published papers (not only accepted)", "Research"),
    ("min_at_institution", "Minimum papers produced at this university", "Research"),
    ("min_class_a_main_author", "Minimum Class A papers as sole or main author", "Research"),
    ("max_books_total", "Maximum books counted", "Research caps"),
    ("max_patents", "Maximum patents counted", "Research caps"),
    ("max_creative_works", "Maximum creative works counted", "Research caps"),
    ("min_referee_reports", "Minimum referee reports", "Referees"),
    ("min_referee_average_pct", "Minimum referee average (percent)", "Referees"),
]


# The few terms the application itself defines (in its rules code), so the assistant can explain them without guessing. Built from the same
# constants the Research agent uses, so the explanation cannot drift from what is applied.
GLOSSARY = [
    {"term": "Class A paper", "meaning": f"A paper in a journal that is indexed in Scopus in the top 20% of its category (SJR percentile of {CLASS_A_MIN_PERCENTILE:g} "
                                          "or more) AND is listed in ISI with an impact factor (policy section 4, page 9)."},
    {"term": "Class B paper", "meaning": "A paper in any other Scopus-indexed journal. A paper in a journal not indexed in Scopus is not counted."},
    {"term": "Sole or main author", "meaning": "The applicant is the only author, or the main (first or corresponding) author, of the paper."},
    {"term": "Submission window", "meaning": "Applications are only accepted in the first week of January, April and October."},
    {"term": "Review stages", "meaning": "After submission the Head of Department and then the Dean review the case, using suggestions prepared by the review agents; "
                                        "the Chancellor's office then selects external referees."},
]


def requirements(s: Session, track: PromotionTrack | None, today: date) -> dict:
    """The policy thresholds for a track and the two scoring forms, as they are in the database. With no track: the two forms only."""
    policy = current_policy(s, today)
    out: dict = {"policy": policy.title, "policy_code": policy.code, "track": None, "thresholds": [], "scoring_forms": []}
    if track is not None:
        row = s.scalar(select(PromotionCriteria).where(PromotionCriteria.policy_version_id == policy.id, PromotionCriteria.track == track))
        out["track"] = TRACK_LABEL[track]
        if row is not None:
            out["thresholds"] = [{"group": g, "label": label, "value": float(getattr(row, f)) if "pct" in f else int(getattr(row, f))}
                                 for f, label, g in CRITERIA_FIELDS]
    for rb in s.scalars(select(Rubric).where(Rubric.policy_version_id == policy.id).order_by(Rubric.id)):
        out["scoring_forms"].append({
            "title": rb.title, "total_points": float(rb.total_points), "pass_points": float(rb.pass_points),
            "items": [{"no": it.item_no, "text": it.text_en, "min": float(it.min_points), "max": float(it.max_points),
                       "full_professor_only": bool(it.full_professor_only)} for it in rb.items
                      if not (it.full_professor_only and track == PromotionTrack.TO_ASSOCIATE)]})
    return out


def _research_rows(r) -> list[dict]:
    rows = [("Total papers submitted for promotion", r.total_papers, r.min_total_publications),
            ("Papers as sole or main author", r.sole_or_main, r.min_sole_main_author),
            ("Published papers (not only accepted)", r.published, r.min_published),
            ("Papers produced at this university", r.at_institution, r.min_at_institution),
            ("Class A papers as sole or main author", r.class_a_sole_or_main, r.min_class_a_main_author)]
    return [{"label": label, "have": have, "need": need, "met": have >= need} for label, have, need in rows]


def dossier_status(s: Session, user_id: int, today: date) -> dict:
    """Where the applicant's application stands: the checklist, the early eligibility checks, the research counts and what is missing."""
    ctx = section11.load(s, user_id, today)
    if ctx.case_id is None:
        return {"has_case": False, "status": None, "editable": False, "track": None, "sections": [], "completed": 0, "total": 0,
                "eligibility_checks": [], "research": None, "window_open": False, "window": "", "can_submit": False,
                "gaps": [{"kind": "start", "what": "Start your application by saving Section 0 (applicant details and promotion track).",
                          "section": "0", "page": SECTION_PATHS["0"]}]}
    case = s.get(PromotionCase, ctx.case_id)
    sections = [{"code": r.code, "title": r.title, "complete": r.complete, "note": r.note, "page": SECTION_PATHS[r.code]} for r in ctx.sections]
    checks = [{"label": c.label, "status": c.status, "detail": c.detail, "policy_ref": c.policy_ref} for c in ctx.eligibility_checks]
    research = _research_rows(ctx.research) if ctx.research else None
    gaps: list[dict] = []
    for r in sections:
        if not r["complete"]:
            gaps.append({"kind": "section", "section": r["code"], "page": r["page"],
                         "what": f"Section {r['code']} ({r['title']}) is incomplete" + (f": {r['note']}" if r["note"] else ".")})
    for c in checks:
        if c["status"] in ("fail", "warn"):
            gaps.append({"kind": "eligibility", "section": "0", "page": SECTION_PATHS["0"],
                         "what": f"Eligibility check '{c['label']}' is {'not met' if c['status'] == 'fail' else 'a warning'}: {c['detail']}"})
    for r in research or []:
        if not r["met"]:
            gaps.append({"kind": "research", "section": "5", "page": SECTION_PATHS["5"],
                         "what": f"{r['label']}: you have {r['have']}, the policy requires {r['need']}."})
    editable = case.status in EDITABLE
    if editable and not ctx.window_open:
        gaps.append({"kind": "window", "section": "11", "page": SECTION_PATHS["11"],
                     "what": f"Submissions are only accepted in the first week of January, April and October ({ctx.window_label})."})
    return {"has_case": True, "status": case.status.value, "editable": editable, "track": TRACK_LABEL.get(case.track),
            "track_code": case.track.value if case.track else None, "sections": sections, "completed": ctx.completed_count,
            "total": len(sections), "eligibility_checks": checks, "research": research, "window_open": ctx.window_open,
            "window": ctx.window_label, "can_submit": ctx.can_submit, "gaps": gaps}


def facts(s: Session, user_id: int, today: date) -> dict:
    """Everything the assistant may use to answer: the status plus the requirements of the applicant's track."""
    status = dossier_status(s, user_id, today)
    track = PromotionTrack(status["track_code"]) if status.get("track_code") else None
    return {"today": today.isoformat(), "status": status, "requirements": requirements(s, track, today), "glossary": GLOSSARY}
