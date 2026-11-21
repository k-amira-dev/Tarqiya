"""Reading documents on this machine: pdfplumber for a PDF with a text layer, OCR for a scan or a picture. No model anywhere."""
import io
from pathlib import Path

import pytest

from promoflow.extraction import local_read
from tests.test_extraction_entry_docs import blank_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"
SCAN_TEXT = "CERTIFICATE OF ATTENDANCE\nThis is to certify that Dr. Nadia Karimi attended the workshop entitled Learning analytics\nheld on 12 March 2024"


def test_a_pdf_with_a_text_layer_is_read_with_pdfplumber():
    data = (FIXTURES / "student_evaluation_b.pdf").read_bytes()
    text, source = local_read.local_text(data)
    assert source == "text" and "Student Evaluation Summary" in text


def test_a_scan_is_read_by_ocr(monkeypatch):
    monkeypatch.setattr(local_read, "ocr_pdf_text", lambda data, max_pages=2: SCAN_TEXT)
    assert local_read.local_text(blank_pdf()) == (SCAN_TEXT, "ocr")                       # a PDF with no text layer


def test_a_picture_is_read_by_ocr(monkeypatch):
    monkeypatch.setattr(local_read, "ocr_image_text", lambda data: SCAN_TEXT)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    assert local_read.local_text(png) == (SCAN_TEXT, "ocr")


def test_a_page_with_almost_nothing_on_it_is_not_a_read(monkeypatch):
    monkeypatch.setattr(local_read, "ocr_pdf_text", lambda data, max_pages=2: "x")
    assert local_read.local_text(blank_pdf()) == ("", "")


def test_ocr_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(local_read, "LOCAL_OCR", False)
    assert local_read.ocr_available() is False
    assert local_read.ocr_pdf_text(blank_pdf()) == "" and local_read.ocr_image_text(b"x") == ""
    assert local_read.local_text(blank_pdf()) == ("", "")


def test_the_helpers_never_raise_on_bad_files():
    assert local_read.tables(b"not a pdf") == [] and local_read.layout_text(b"not a pdf") == ""
    assert local_read.ocr_pdf_text(b"not a pdf") == "" and local_read.ocr_image_text(b"not a picture") == ""
    assert local_read.local_text(b"not a pdf") == ("", "") and local_read.local_text(b"") == ("", "")


def test_real_ocr_reads_a_drawn_certificate_line():
    pytest.importorskip("rapidocr")
    from PIL import Image, ImageDraw, ImageFont

    font_file = Path(r"C:\Windows\Fonts\arial.ttf")
    if not font_file.exists():
        pytest.skip("no TrueType font to draw with")
    image = Image.new("RGB", (1500, 380), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_file), 56)
    draw.text((40, 30), "CERTIFICATE OF ATTENDANCE", fill="black", font=font)
    draw.text((40, 130), "Certificate No. ATT-2024-170", fill="black", font=font)
    draw.text((40, 230), "Dr. Nadia Karimi attended the workshop", fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    text, source = local_read.local_text(buf.getvalue())
    assert source == "ocr" and "ATT-2024-170" in text.replace(" ", "") and "ATTENDANCE" in text.upper()
