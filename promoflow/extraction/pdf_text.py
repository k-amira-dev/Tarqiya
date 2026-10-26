"""Step 1 of the autofill: get the text out of an uploaded PDF.

`extract_text(data)` NEVER raises. Whatever the file is (a normal PDF, a scan, a broken file, an encrypted file, not a
PDF at all) it returns an `ExtractedText` whose `status` says what happened, so the upload page can show a plain
message and let the applicant type the values by hand instead.

Limits: only the first MAX_PAGES pages are read and the text is cut at MAX_CHARS. Evidence documents are short; the
limits only protect the page and the model from a huge file.
"""
import io
import re
from dataclasses import dataclass

from pypdf import PdfReader

MAX_PAGES = 10
MAX_CHARS = 20_000

OK = "ok"                    # text found
EMPTY = "empty"              # a valid PDF with no text layer, e.g. a scan or a photo
UNREADABLE = "unreadable"    # broken, encrypted or not a PDF


@dataclass(frozen=True)
class ExtractedText:
    status: str              # OK | EMPTY | UNREADABLE
    text: str                # the cleaned text ("" unless status is OK)
    pages: int               # pages in the file (0 if unreadable)
    truncated: bool          # True if pages or characters were cut off
    message: str             # a sentence safe to show to the applicant (empty when OK)

    @property
    def ok(self) -> bool:
        return self.status == OK


def _clean(raw: str) -> str:
    """Tidy extracted text: no stray spaces or blank lines, so one printed line stays one line of text."""
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_text(data: bytes) -> ExtractedText:
    """The text of a PDF given as bytes (what st.file_uploader().getvalue() returns)."""
    if not data:
        return ExtractedText(UNREADABLE, "", 0, False, "The file is empty.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return ExtractedText(UNREADABLE, "", 0, False,
                                 "The PDF is password-protected, so it cannot be read. Please enter the values by hand.")
        total = len(reader.pages)
        parts = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
    except Exception:       # pypdf raises many different errors for damaged or non-PDF files
        return ExtractedText(UNREADABLE, "", 0, False,
                             "This file could not be read as a PDF. Please enter the values by hand.")

    text = _clean("\n".join(parts))
    truncated = total > MAX_PAGES or len(text) > MAX_CHARS
    text = text[:MAX_CHARS]
    if not text:
        return ExtractedText(EMPTY, "", total, False,
                             "No text was found in this PDF (it may be a scan or a photo). "
                             "Please enter the values by hand.")
    return ExtractedText(OK, text, total, truncated, "")
