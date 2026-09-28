"""Deterministic Research Agent rules that don't need an LLM (spec §9): journal classification and the ISBN
checksum. Counts, caps and the supervision-rule cross-check are Research Agent features, not built yet.
"""
import re
from decimal import Decimal

from promoflow.db.enums import JournalClass

CLASS_A_MIN_PERCENTILE = Decimal("80")


def classify_journal(*, scopus_indexed: bool, sjr_percentile: Decimal | None, isi_listed: bool,
                     has_impact_factor: bool) -> JournalClass:
    """Class A = Scopus top-20% SJR and listed in ISI with an impact factor (spec §5A, policy §4 p.9)."""
    if not scopus_indexed:
        return JournalClass.NOT_COUNTED
    if isi_listed and has_impact_factor and sjr_percentile is not None and sjr_percentile >= CLASS_A_MIN_PERCENTILE:
        return JournalClass.CLASS_A
    return JournalClass.CLASS_B


_ISBN_CHARS = re.compile(r"^[\dXx-]+$")


def isbn_is_valid(isbn: str) -> bool:
    """ISBN-10 (MOD 11) or ISBN-13 (EAN-13 MOD 10) checksum, ignoring hyphens."""
    if not _ISBN_CHARS.match(isbn):
        return False
    digits = isbn.replace("-", "").upper()
    if len(digits) == 10:
        if not digits[:-1].isdigit() or digits[-1] not in "0123456789X":
            return False
        total = sum((10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(digits))
        return total % 11 == 0
    if len(digits) == 13:
        if not digits.isdigit():
            return False
        total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(digits))
        return total % 10 == 0
    return False
