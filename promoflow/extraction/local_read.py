"""Read documents ON THIS MACHINE: no model, no tokens, nothing leaves the server.

The whole app reads uploads through `local_text`: pdfplumber for a PDF with a text layer, OCR for a scan or a picture. There is no
language model anywhere in reading a document.
  * `ocr_pdf_text` / `ocr_image_text`: local OCR (RapidOCR) turns a scanned page or a photo into text.
  * `tables` / `layout_text`: pdfplumber reads the tables and the layout of a normal (text) PDF. The fixed-layout reports (registrar load,
    student evaluations, advising lists, peer observations) come out as clean rows, so a plain parser can read them with no model at all.

Everything here degrades quietly: if a library is missing or a file is odd, the function returns "" or [] and the caller falls back to the
older route. Nothing here touches the database.
"""
import io
import threading
import unicodedata

from promoflow.config import LOCAL_OCR

MIN_TEXT_CHARS = 150           # less text than this in a PDF = a scan or a photo: read it with OCR instead
MIN_OCR_CHARS = 60             # less than this from OCR = the page is unreadable (blank, or a photo with no text)


class ReadFailed(Exception):
    """A file could not be read on this machine; the message is plain and safe to show to the applicant."""


OCR_DPI = 200                  # 200 dpi reads small print reliably; 110 dpi (used for the vision model) is too coarse for OCR
OCR_MAX_PAGES = 2              # same limit as the picture route: evidence letters are one page, two are read in case of a back page

# The PDF renderer (pdfium) crashes if two threads use it at once. Every renderer in the project shares THIS lock.
PDFIUM_LOCK = threading.Lock()

_OCR_LOCK = threading.Lock()   # one page at a time through the OCR engine: it is CPU-bound anyway
_engine = None
_engine_failed = False


def ocr_available() -> bool:
    """True when local OCR is switched on (LOCAL_OCR) and the library can be loaded."""
    global _engine, _engine_failed
    if not LOCAL_OCR or _engine_failed:
        return False
    if _engine is not None:
        return True
    with _OCR_LOCK:
        if _engine is None:
            try:
                from rapidocr import RapidOCR

                _engine = RapidOCR()
            except Exception:                         # not installed, or the models are missing: use the older route
                _engine_failed = True
                return False
    return True


def _tidy(lines) -> str:
    # NFKC turns the shaped Arabic letters a document may store back into plain ones (same as the text route).
    return unicodedata.normalize("NFKC", "\n".join(x.strip() for x in lines if x and x.strip()))


def _ocr_array(image) -> str:
    with _OCR_LOCK:
        result = _engine(image)
    return _tidy(result.txts or [])


def ocr_image_text(data: bytes) -> str:
    """The text of a picture (PNG or JPEG bytes), read locally. "" when OCR is unavailable or nothing was read."""
    if not ocr_available():
        return ""
    try:
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(data)).convert("RGB")
        image.thumbnail((2400, 2400))
        return _ocr_array(np.array(image))
    except Exception:
        return ""


def ocr_pdf_text(data: bytes, max_pages: int = OCR_MAX_PAGES) -> str:
    """The text of the first pages of a scanned PDF, read locally. "" when OCR is unavailable or nothing was read."""
    if not ocr_available():
        return ""
    try:
        import numpy as np
        import pypdfium2 as pdfium

        pages = []
        with PDFIUM_LOCK:                              # only the rendering waits; the OCR below runs outside the lock
            pdf = pdfium.PdfDocument(data)
            try:
                for i in range(min(len(pdf), max_pages)):
                    pages.append(np.array(pdf[i].render(scale=OCR_DPI / 72).to_pil().convert("RGB")))
            finally:
                pdf.close()
        return "\n".join(t for t in (_ocr_array(p) for p in pages) if t)
    except Exception:
        return ""


# ---- normal (text) PDFs: tables and layout ------------------------------------------------------------------------

def tables(data: bytes, max_pages: int = 40) -> list[list[list[str]]]:
    """Every table in a text PDF, page after page, as rows of cleaned cell text ("" for an empty cell). [] if none or unreadable.

    A table that continues on the next page comes back as separate tables; the caller joins them (the header row repeats)."""
    try:
        import pdfplumber

        out = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:max_pages]:
                for tb in page.extract_tables():
                    out.append([[" ".join((c or "").split()) for c in row] for row in tb])
        return out
    except Exception:
        return []


def layout_text(data: bytes, max_pages: int = 40) -> str:
    """The text of a text PDF in reading order with pdfplumber (better than pypdf on columns and tables). "" if unreadable."""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return _tidy("\n".join(p.extract_text() or "" for p in pdf.pages[:max_pages]).splitlines())
    except Exception:
        return ""


# ---- the one entry point every reader uses ---------------------------------------------------------------------------------------

def is_image(data: bytes) -> bool:
    return data[:4] == bytes([0x89, 0x50, 0x4E, 0x47]) or data[:3] == bytes([0xFF, 0xD8, 0xFF])      # PNG or JPEG


def local_text(data: bytes) -> tuple[str, str]:
    """The text of an uploaded file, read on this machine: (text, source). source is "text" (a PDF's own text layer, read with pdfplumber),
    "ocr" (a scanned PDF or a picture, read with OCR) or "" (nothing could be read: a blank page, a damaged file, OCR not installed)."""
    if not is_image(data):
        text = layout_text(data, max_pages=10)
        if len(text) >= MIN_TEXT_CHARS:
            return text[:20_000], "text"
        ocr = ocr_pdf_text(data)
    else:
        ocr = ocr_image_text(data)
    return (ocr, "ocr") if len(ocr) >= MIN_OCR_CHARS else ("", "")
