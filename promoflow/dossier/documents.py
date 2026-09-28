"""Shared CaseDocument helpers: every section attaches evidence the same way (spec §2.4), whether it's a
section-level file (entity_table/entity_id = NULL) or one entry's evidence (e.g. one degree's certificate).

`slot` tells apart several files of the same kind on the same entity (a degree's "certificate" vs its
"equivalency" certificate); most callers don't need it and leave it NULL.
"""
import mimetypes
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow import storage
from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument

MAX_FILENAME = 300


def current(s: Session, case_id: int, section_code: str, kind: DocumentKind, *,
           entity_table: str | None = None, entity_id: int | None = None, slot: str | None = None
           ) -> CaseDocument | None:
    return s.scalar(select(CaseDocument).where(
        CaseDocument.case_id == case_id, CaseDocument.section_code == section_code, CaseDocument.kind == kind,
        CaseDocument.entity_table == entity_table, CaseDocument.entity_id == entity_id, CaseDocument.slot == slot,
        CaseDocument.superseded_by_id.is_(None),
    ))


def replace(s: Session, case_id: int, user_id: int, section_code: str, kind: DocumentKind,
           filename: str, data: bytes, *, entity_table: str | None = None, entity_id: int | None = None,
           slot: str | None = None, signed_date: date | None = None) -> CaseDocument:
    """Store a newly uploaded file and mark any earlier one in the same slot as superseded."""
    old = current(s, case_id, section_code, kind, entity_table=entity_table, entity_id=entity_id, slot=slot)
    stored_path, sha256 = storage.save(case_id, filename, data)
    doc = CaseDocument(
        case_id=case_id, section_code=section_code, entity_table=entity_table, entity_id=entity_id,
        kind=kind, slot=slot, original_filename=filename[:MAX_FILENAME], stored_path=stored_path,
        mime_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        size_bytes=len(data), sha256=sha256, signed_date=signed_date, uploaded_by=user_id,
    )
    s.add(doc)
    s.flush()
    if old is not None:
        old.superseded_by_id = doc.id
    return doc
