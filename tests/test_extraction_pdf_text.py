"""Text extraction from uploaded PDFs. The two fixture files are fictional sample evidence from the test dossiers."""
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from promoflow.extraction import pdf_text
from promoflow.extraction.pdf_text import EMPTY, MAX_PAGES, OK, UNREADABLE, extract_text

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _pdf(writer: PdfWriter) -> bytes:
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_student_evaluation_text_is_read():
    r = extract_text(_bytes("student_evaluation_b.pdf"))
    assert r.status == OK and r.ok and r.pages == 1 and not r.truncated
    # The values the autofill will need are present, one printed line per text line.
    assert "ELEC300 Introduction to Electrical Engineering (2019/2020 Fall)" in r.text
    assert "Enrolled students: 51" in r.text
    assert "Respondents: 39" in r.text
    assert "Average score: 4.3 out of 5" in r.text


def test_other_document_style_is_read_too():
    r = extract_text(_bytes("course_file_a.pdf"))
    assert r.ok
    assert "MEC-210" in r.text and "4.8/5 from 35 respondents" in r.text


def test_blank_pdf_is_reported_as_empty():
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    r = extract_text(_pdf(w))
    assert r.status == EMPTY and r.text == "" and r.pages == 1 and "enter the values by hand" in r.message


def test_not_a_pdf_and_empty_bytes_are_unreadable_not_errors():
    assert extract_text(b"hello, this is not a pdf").status == UNREADABLE
    assert extract_text(b"%PDF-1.7 broken").status == UNREADABLE
    assert extract_text(b"").status == UNREADABLE


def test_encrypted_pdf_is_unreadable():
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    w.encrypt("secret")
    r = extract_text(_pdf(w))
    assert r.status == UNREADABLE and "password" in r.message


def test_only_the_first_pages_are_read():
    page = PdfReader(io.BytesIO(_bytes("student_evaluation_b.pdf"))).pages[0]
    w = PdfWriter()
    for _ in range(MAX_PAGES + 3):
        w.add_page(page)
    r = extract_text(_pdf(w))
    assert r.ok and r.pages == MAX_PAGES + 3 and r.truncated
    assert r.text.count("Respondents: 39") == MAX_PAGES


def test_text_is_cut_at_the_character_limit(monkeypatch):
    monkeypatch.setattr(pdf_text, "MAX_CHARS", 40)
    r = extract_text(_bytes("student_evaluation_b.pdf"))
    assert r.ok and len(r.text) == 40 and r.truncated


def test_cleaning_collapses_spaces_and_blank_lines():
    assert pdf_text._clean("  a   b \n\n \t\n c d  ") == "a b\nc d"
