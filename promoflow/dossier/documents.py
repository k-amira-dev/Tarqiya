"""Shared CaseDocument helpers: every section attaches evidence the same way (spec §2.4), whether it's a
section-level file (entity_table/entity_id = NULL) or one entry's evidence (e.g. one degree's certificate).

`slot` tells apart several files of the same kind on the same entity (a degree's "certificate" vs its
"equivalency" certificate); most callers don't need it and leave it NULL.

HOW FILE REPLACEMENT WORKS: files are never deleted. When an applicant uploads a new version, the old row is kept and
marked "superseded" (its `superseded_by_id` points at the new one). So `current()` means "the one that is not superseded",
and the history of every upload stays available to the reviewers.
"""
import mimetypes
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow import storage
from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument

# Longest original file name we keep (it is shown to people; the stored name is made safe in storage.py).
MAX_FILENAME = 300
# A key under which a per-session cache of documents is kept (see _entity_documents).
_PREFETCH = "document_prefetch"


# A speed trick: one query fetches the files of EVERY row of an entry type at once, and remembers them for this
# database session.
def _entity_documents(s: Session, case_id: int, section_code: str, entity_table: str) -> dict:
    """Every current file of one entry type, fetched with a single query and remembered on the session.

    Loaders ask for each row's file one by one; without this each row would cost a ~190 ms round trip.
    """
    # `s.info` is a scratch dictionary that lives as long as this database session does.
    cache = s.info.setdefault(_PREFETCH, {})
    key = (case_id, section_code, entity_table)
    if key not in cache:
        cache[key] = {
            (d.entity_id, d.kind, d.slot): d
            for d in s.scalars(select(CaseDocument).where(
                CaseDocument.case_id == case_id, CaseDocument.section_code == section_code,
                CaseDocument.entity_table == entity_table, CaseDocument.superseded_by_id.is_(None)))
        }
    return cache[key]


# The current (not superseded) file in a place, or None. A place is a section, a kind of file and, for a file about
# one entry, which entry; `slot` tells apart two files of the same kind on the same entry.
def current(s: Session, case_id: int, section_code: str, kind: DocumentKind, *,
           entity_table: str | None = None, entity_id: int | None = None, slot: str | None = None
           ) -> CaseDocument | None:
    # A file about one specific entry (for example one degree's certificate): use the prefetched cache.
    if entity_table is not None and entity_id is not None:
        return _entity_documents(s, case_id, section_code, entity_table).get((entity_id, kind, slot))
    return s.scalar(select(CaseDocument).where(
        CaseDocument.case_id == case_id, CaseDocument.section_code == section_code, CaseDocument.kind == kind,
        CaseDocument.entity_table == entity_table, CaseDocument.entity_id == entity_id, CaseDocument.slot == slot,
        CaseDocument.superseded_by_id.is_(None),
    ))


# Save a new upload. The file is written to disk (storage.py), a new case_document row is added, and the earlier
# file in the same place is marked as superseded.
def replace(s: Session, case_id: int, user_id: int, section_code: str, kind: DocumentKind,
           filename: str, data: bytes, *, entity_table: str | None = None, entity_id: int | None = None,
           slot: str | None = None, signed_date: date | None = None) -> CaseDocument:
    """Store a newly uploaded file and mark any earlier one in the same slot as superseded."""
    # Forget the cached documents: they are about to change.
    s.info.pop(_PREFETCH, None)  # the remembered files are about to change
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
    s.info.pop(_PREFETCH, None)
    return doc
