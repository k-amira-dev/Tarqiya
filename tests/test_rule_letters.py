"""Scanned letters read by plain rules on the OCR text, and how read_entries uses them: the text comes from pdfplumber or OCR, the rules fill the
values, and the applicant completes what they miss. The sample texts are real OCR output, spacing slips included."""
from datetime import date

import pytest

from promoflow.extraction import entry_docs as E, local_read, rule_letters as R
from promoflow.extraction.local_read import ReadFailed

COMMITTEE = """University of Sharjah
Department of Computer Science
Letter ofAppointment to a Committee
Ref: COM/2020/152 Date: 01 September 2020
To: Dr. Nadia Karimi, Department of Computer Science
I am pleased to inform you that you have been appointed as Member of the Department Quality
Assurance Committee, from 01 September 2020 to 31August 2023.
Dr. Samer Khoury
OFFICIAL
Head, Department of Computer Science"""

ADMIN = """Decision on Assignment to an Administrative Position
it has been decided that Dr. Nadia
Karimi, Assistant Professor in the Department of Computer Science, is assigned as Coordinator,
Networking Laboratory, from 01September 2020to 31 August 2022.
Dr. SamerKhoury
Head, Department of Computer Science"""

WORKSHOP = """COLLEGE OF COMPUTING AND INFORMATICS
CERTIFICATE OF
APPRECIATION
The College of Communication confirms that
Dr. Nadia Karimi
acted as organiser of the workshop
"Capture-the-Flag Training Day"
held on o8 November 2023 at College of Computing and Informatics,
University of Sharjah, with 55 participants."""

TRAINING = """CEDARLINK TELECOM
CERTIFICATE OF APPRECIATION
Cedarlink Telecom thanks
Dr. Nadia Karimi
for delivering a 8-hour training entitled
"Python for data analysis"
on 12 June 2019."""

ATTENDANCE = """TEACHING AND LEARNING CENTRE, UNIVERSITY OF SHARJAH
CERTIFICATE OF ATTENDANCE
This is to certify that
Dr. Nadia Karimi
attended the workshop entitled
"Learning analytics for instructors"
held on 12 March 2024, with a total of 4 training hours."""

COMMUNITY = """NATIONAL YOUTH TECHNOLOGY COUNCIL
LETTER OF APPRECIATION
National Youth Technology Council would like to thank
Dr. Nadia Karimi
for serving as judge in
"National student programming competition"
between April 2022 and April 2024.
2 editions judged, 60 entries assessed.
Director"""


def test_a_committee_letter_with_dropped_spaces_is_read():
    got = R.committee_letter(COMMITTEE)
    assert got == {"committee_name": "Department Quality Assurance Committee", "role": "Member", "date_from": "01 September 2020",
                   "date_to": "31 August 2023", "signer_title": "Head, Department of Computer Science"}
    assert R.missing("committee", got) == []


def test_open_ended_appointments_have_no_end_date():
    got = R.committee_letter(COMMITTEE.replace("to 31August 2023", "until further notice"))
    assert got["date_from"] == "01 September 2020" and got["date_to"] is None


def test_an_admin_decision_gives_position_and_dates():
    got = R.admin_letter(ADMIN)
    assert got["position_title"] == "Coordinator, Networking Laboratory"
    assert (got["date_from"], got["date_to"]) == ("01 September 2020", "31 August 2022")


def test_a_workshop_with_an_ocr_slip_in_the_day_is_read():
    got = R.workshop_cert(WORKSHOP)
    assert got["title"] == "Capture-the-Flag Training Day" and got["activity_date"] == "08 November 2023"
    assert got["role"] == "organiser" and got["attendees"] == 55 and got["organized_by"] == "COLLEGE OF COMPUTING AND INFORMATICS"


def test_training_attendance_and_community_letters():
    t = R.training_cert(TRAINING)
    assert (t["title"], t["hours"], t["activity_date"], t["host_organisation"]) == ("Python for data analysis", 8.0, "12 June 2019", "CEDARLINK TELECOM")
    a = R.attendance_cert(ATTENDANCE)
    assert (a["title"], a["hours"], a["event_type"], a["activity_date"]) == ("Learning analytics for instructors", 4.0, "workshop", "12 March 2024")
    c = R.community_letter(COMMUNITY)
    assert (c["role"], c["date_from"], c["date_to"], c["outputs"]) == ("judge", "April 2022", "April 2024", "2 editions judged, 60 entries assessed")


def test_unfamiliar_wording_gives_blanks_not_guesses():
    got = R.committee_letter("Dear Dr. Karimi,\nWe are pleased to appoint you as Chair of the Curriculum Committee for the period 1 September 2020 - 31 August 2023.")
    assert got["committee_name"] is None and got["role"] is None
    assert R.missing("committee", got) == ["committee_name", "role", "date_from"]


# ---- how read_entries uses them ---------------------------------------------------------------------------------------

def feed(monkeypatch, text, source="ocr"):
    """Make the reader return this text for any file ("" = nothing could be read)."""
    monkeypatch.setattr(local_read, "local_text", lambda data: (text, source) if text else ("", ""))


CTX = E.Ctx(applicant_name="Dr. Nadia Karimi")


def test_a_complete_read_gives_a_ready_draft(monkeypatch):
    feed(monkeypatch, COMMITTEE)
    drafts = E.read_entries(E.KINDS["committee"], "c.pdf", b"x", CTX)
    d = drafts[0]
    assert len(drafts) == 1 and d.route == "ocr" and d.ok
    assert d.values["committee_name"] == "Department Quality Assurance Committee" and d.values["date_from"] == date(2020, 9, 1)
    assert d.values["level"] == "department" and d.values["role_code"] == "member"
    feed(monkeypatch, COMMITTEE, "text")
    assert E.read_entries(E.KINDS["committee"], "c.pdf", b"x", CTX)[0].route == "text"


def test_an_incomplete_read_keeps_what_was_found_and_asks_for_the_rest(monkeypatch):
    feed(monkeypatch, "Letter of Appointment\nyou are appointed to something, from 01 September 2024 until further notice.")
    d = E.read_entries(E.KINDS["committee"], "c.pdf", b"x", CTX)[0]
    assert not d.ok and d.values["date_from"] == date(2024, 9, 1) and "committee name not found" in d.issues


def test_a_file_nothing_can_read_fails_plainly(monkeypatch):
    feed(monkeypatch, "")
    with pytest.raises(ReadFailed, match="enter the values by hand"):
        E.read_entries(E.KINDS["committee"], "c.pdf", b"x", CTX)


def test_every_kind_of_upload_in_the_app_has_a_local_reader():
    """The whole app reads documents the same way: nothing is left that needs a model."""
    assert set(E.KINDS) - {"curriculum"} == set(E.RULE_KINDS)                 # the curriculum summary has its own table reader
    assert set(E.RULE_KINDS.values()) <= set(R.RULES) and all(k in R.REQUIRED for k in set(E.RULE_KINDS.values()))
