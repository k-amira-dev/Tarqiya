"""5F – Scopus evidence & journal ranking screenshots (spec §9): one record per case.

The "within 30 days of submission" rule is checked at submission (§11), not while drafting, since the
submission date isn't known yet. Per-journal ranking screenshots (one per distinct §5A journal) aren't
built yet.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, ScopusEvidence
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_new_entry

FIELDS = ["h_index", "total_citations", "screenshot_date"]
SCREENSHOT_SLOT = "scopus_screenshot"


@dataclass(frozen=True)
class Section5FContext:
    evidence: ScopusEvidence | None
    screenshot: CaseDocument | None


def load(s: Session, case_id: int) -> Section5FContext:
    evidence = s.scalar(select(ScopusEvidence).where(ScopusEvidence.case_id == case_id))
    screenshot = documents.current(s, case_id, "5F", DocumentKind.SCREENSHOT, slot=SCREENSHOT_SLOT)
    return Section5FContext(evidence, screenshot)


def validate(values: dict, today: date, has_screenshot: bool, upload=None) -> list[str]:
    errors = []
    h_index, citations, screenshot_date = values.get("h_index"), values.get("total_citations"), values.get("screenshot_date")
    if h_index is None or not (0 <= h_index <= 300):
        errors.append("h-index must be between 0 and 300.")
    if citations is None or citations < 0:
        errors.append("Total citations must be 0 or more.")
    if not screenshot_date:
        errors.append("Enter the screenshot date.")
    elif screenshot_date > today:
        errors.append("Screenshot date cannot be in the future.")
    if upload is None and not has_screenshot:
        errors.append("Upload your Scopus profile screenshot.")
    return errors


def save(s: Session, user_id: int, values: dict, upload: tuple[str, bytes] | None = None) -> None:
    case = case_for_new_entry(s, user_id)
    evidence = s.scalar(select(ScopusEvidence).where(ScopusEvidence.case_id == case.id))
    if evidence is None:
        evidence = ScopusEvidence(case_id=case.id, **{f: values.get(f) for f in FIELDS})
        s.add(evidence)
        before = None
    else:
        before = audit.snapshot(evidence, FIELDS)
        for f in FIELDS:
            setattr(evidence, f, values.get(f))
    s.flush()
    if upload is not None:
        filename, data = upload
        documents.replace(s, case.id, user_id, "5F", DocumentKind.SCREENSHOT, filename, data, slot=SCREENSHOT_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5f_saved", entity_table="scopus_evidence",
             entity_id=evidence.id, before=before, after=audit.snapshot(evidence, FIELDS))
