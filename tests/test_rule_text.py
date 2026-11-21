"""Text documents read by plain rules (no model): papers, acceptance letters, book chapters, conference papers, funded projects, peer observations,
equivalency certificates, employment contracts, recommendation letters, innovation reports, signed documents, and the curriculum table.
The texts are what pdfplumber returned for the pilot dossier's PDFs."""
import subprocess
import sys

from promoflow.extraction import entry_docs as E, local_read, rule_letters as R, rule_reports as RR
from tests.test_rule_letters import CTX, feed

PAPER = """Journal of Network and Intelligent Systems Vol. 71, 2023, pp. 103312
Meridian Academic Publishers DOI: 10.9999/pf.cs01.001 (invented)
Communication-Efficient Federated Learning for Intrusion
Detection in 5G Edge Networks
N. Karimi, T. Okonkwo, S. Lindqvist
Department of Computer Science, College of Computing and Informatics, University of Sharjah, United Arab Emirates
Abstract. Researchers have increasingly examined encrypted traffic classification."""

PAPER_ISSUE = PAPER.replace("Vol. 71, 2023, pp. 103312", "Vol. 45, No. 3, 2025, pp. 211-246")
PAPER_ACCEPTED = """Journal of Network and Intelligent Systems Accepted manuscript (not yet published)
Meridian Academic Publishers DOI: 10.9999/pf.cs01.008 (invented)
Multi-Agent Reinforcement Learning for Dynamic Spectrum
Allocation in 6G Networks
T. Okonkwo, N. Karimi
Department of Computer Science, College of Computing and Informatics, University of Sharjah, United Arab Emirates
Abstract. Researchers have increasingly examined explainable machine learning."""

ACCEPTANCE = """Editorial Office
Journal of Network and Intelligent Systems
Meridian Academic Publishers
Date: 12 September 2026
Manuscript ID: JNIS-2026-80417
Dear Dr. Karimi,
We are pleased to inform you that your manuscript entitled
"Multi-Agent Reinforcement Learning for Dynamic Spectrum Allocation in 6G Networks"
(authors: T. Okonkwo, N. Karimi) has been reviewed by the editorial board and by two independent
reviewers, and has been accepted for publication in Journal of Network and Intelligent Systems.
The article will be published in an upcoming issue."""

BOOK = """NORTHGATE ACADEMIC PRESS
Intelligent Networking: Methods and
Applications
Edited by P. Whitfield and R. Banerjee
First published 2024
ISBN 978-0-0000-0000-0 (simulated)
Contents: Chapter 9, pp. 142-165
Foundations of Agentic AI for Network Management
Nadia Karimi
University of Sharjah, United Arab Emirates"""

CONFERENCE_1 = """International Conference on Intelligent Networks and Security Dubai, UAE
14 November 2022 · Proceedings, pp.
(ICINS 2022)
112-119
Organised by Gulf Computing Research Association
Lightweight Federated Anomaly Detection on Edge Gateways
Nadia Karimi
University of Sharjah, United Arab Emirates · nadia.karimi@promoflow.test"""

CONFERENCE_2 = """Arab Computing Research Forum 2025 Doha, Qatar
Organised by Arab Computing Research Forum Secretariat 20 March 2025 · Proceedings, pp. 44-51
Agentic Workflows for Network Operations: Early Evidence
Nadia Karimi
University of Sharjah, United Arab Emirates · nadia.karimi@promoflow.test"""

FUNDED = """University of Sharjah · Office of Research Ref: CRG/2022/CS/0412
RESEARCH GRANT AWARD AND PROJECT DESCRIPTION
Project title Resilient Federated Learning for Campus IoT Security
Funding body University of Sharjah Competitive Research Grant Programme (Internal
(university))
Amount awarded AED 120,000
Project period 01 January 2023 – 31 December 2024
Principal Investigator Dr. Nadia Karimi – Department of Computer Science
Co-investigators Dr. Amal Rahmani
Status Completed (final report approved)
Summary"""

PEER = """University of Sharjah Teaching and Learning Committee
Peer Observation of Teaching - Report
Faculty member Dr. Nadia Karimi Date of 15 October 2019
observed observation
Course CS 325 Network Security (CRN 10281) Semester Fall 2019
Observer Prof. Karim Al-Masri Observer role Peer faculty member
Evaluation criteria (scale 1 = poor, 5 = excellent)
Overall score (out of 5) 4.17
Strengths"""

EMPLOYMENT = """Lebanon
Cedarlink Telecom
Ref: CLT/EMP/2008/0198
EMPLOYMENT CONTRACT
This contract is made on 20 June 2008 between Cedarlink Telecom (the "Employer") and Nadia
Karimi, Lebanese national (the "Employee").
The Employee is employed as Network Engineer in the Network Operations Department.
The contract starts on 01 July 2008 and ends on 31 August 2008, unless terminated earlier."""

LETTER = """Prof. Helen Marsh
Westmarch University, Australia
Professor of Computer Science
13 October 2026
I write with pleasure in support of Dr. Karimi's application for promotion. I supervised Dr.
Karimi's doctoral research at Westmarch University and have followed the progress of the career."""

INNOVATION_CASE = """Teaching Innovation Report
Flipped versus traditional delivery in Data Structures and Algorithms
INSTRUCTOR COURSE / TERM
N. Karimi, Department of Computer Science CS 220, Spring 2023 (CRN 10545; 47 students
Background
Concerned that long lectures left little room, the instructor compared two ways of delivering CS 220.
Method
Both offerings used the same learning outcomes and the same final examination.
Findings
The pass rate rose from 88% to 94%.
Reflection
The flipped format worked."""


def test_a_paper_header_gives_journal_publisher_doi_title_and_authors():
    p = R.RULES["paper"](PAPER)
    assert (p["journal_name"], p["volume"], p["year"], p["pages"], p["publisher"], p["doi"]) == (
        "Journal of Network and Intelligent Systems", "71", 2023, "103312", "Meridian Academic Publishers", "10.9999/pf.cs01.001")
    assert p["title"] == "Communication-Efficient Federated Learning for Intrusion Detection in 5G Edge Networks"
    assert p["authors"] == ["N. Karimi", "T. Okonkwo", "S. Lindqvist"] and p["affiliation"].startswith("Department of Computer Science")
    assert R.missing("paper", p) == []
    q = R.RULES["paper"](PAPER_ISSUE)
    assert (q["volume"], q["issue"], q["year"], q["pages"]) == ("45", "3", 2025, "211-246")


def test_an_accepted_manuscript_has_a_journal_but_no_volume_or_year():
    p = R.RULES["paper"](PAPER_ACCEPTED)
    assert p["journal_name"] == "Journal of Network and Intelligent Systems" and p["year"] is None and p["volume"] is None
    assert p["authors"] == ["T. Okonkwo", "N. Karimi"] and R.missing("paper", p) == []


def test_acceptance_letter():
    a = R.RULES["acceptance"](ACCEPTANCE)
    assert a["title"].startswith("Multi-Agent Reinforcement Learning") and a["journal_name"] == "Journal of Network and Intelligent Systems"
    assert (a["publisher"], a["acceptance_date"], a["authors"]) == ("Meridian Academic Publishers", "12 September 2026", ["T. Okonkwo", "N. Karimi"])


def test_book_chapter():
    b = R.RULES["book"](BOOK)
    assert (b["book_title"], b["chapter_title"], b["publisher"], b["publication_year"], b["isbn"], b["authors"]) == (
        "Intelligent Networking: Methods and Applications", "Foundations of Agentic AI for Network Management", "Northgate Academic Press", 2024,
        "978-0-0000-0000-0", ["Nadia Karimi"])


def test_conference_paper_in_both_header_layouts():
    a = R.RULES["conference"](CONFERENCE_1)
    assert (a["conference_title"], a["place"], a["organizer"], a["pages"], a["conference_date"]) == (
        "International Conference on Intelligent Networks and Security (ICINS 2022)", "Dubai, UAE", "Gulf Computing Research Association", "112-119", "14 November 2022")
    assert a["title"] == "Lightweight Federated Anomaly Detection on Edge Gateways" and a["authors"] == ["Nadia Karimi"]
    b = R.RULES["conference"](CONFERENCE_2)
    assert (b["conference_title"], b["place"], b["organizer"], b["pages"], b["conference_date"]) == (
        "Arab Computing Research Forum 2025", "Doha, Qatar", "Arab Computing Research Forum Secretariat", "44-51", "20 March 2025")


def test_funded_project_role_is_the_applicants_own():
    f = R.RULES["funded"](FUNDED, "Dr. Nadia Karimi")
    assert (f["amount"], f["currency"], f["start_date"], f["end_date"], f["applicant_role"], f["status"]) == (
        120000.0, "AED", "01 January 2023", "31 December 2024", "Principal Investigator", "Completed")
    assert R.RULES["funded"](FUNDED, "Dr. Amal Rahmani")["applicant_role"] == "Co-investigator"


def test_peer_observation_employment_and_letter():
    p = R.RULES["peer"](PEER)
    assert (p["course_code"], p["term"], p["observer_name"], p["observation_date"], p["overall_score"], p["scale_max"]) == (
        "CS 325", "Fall 2019", "Prof. Karim Al-Masri", "15 October 2019", 4.17, 5.0)
    e = R.RULES["position"](EMPLOYMENT)
    assert (e["position"], e["employer"], e["country"], e["date_from"], e["date_to"]) == ("Network Engineer", "Cedarlink Telecom", "Lebanon", "01 July 2008", "31 August 2008")
    letter = R.RULES["letter"](LETTER)
    assert letter["writer_name"] == "Prof. Helen Marsh" and letter["writer_institution"] == "Westmarch University, Australia"
    assert letter["relationship"].startswith("I supervised Dr. Karimi's doctoral research")          # "Dr." does not end the sentence


def test_innovation_report_sections_in_the_other_layouts():
    i = R.RULES["innovation"](INNOVATION_CASE)
    assert (i["title"], i["course_code"], i["term"]) == ("Flipped versus traditional delivery in Data Structures and Algorithms", "CS 220", "Spring 2023")
    assert i["what_was_done"].startswith("Both offerings") and i["measured_outcome"] == "The pass rate rose from 88% to 94%"


def test_signed_date_prefers_a_labelled_date():
    assert R.RULES["signed"]("Dr. Nadia Karimi\nLast updated: 06 November 2026\nDepartment of CS")["signed_date"] == "06 November 2026"
    assert R.RULES["signed"]("Dear Committee, 3 May 2026. Sincerely")["signed_date"] == "3 May 2026"


def test_the_curriculum_table_gives_one_entry_per_row(monkeypatch):
    table = [[["Course", "Contribution", "Year", "Approved by", "What the faculty member did"],
              ["CS 415 Deep Learning", "Proposed a new course New course", "2021", "University level 12 May 2021", "Designed the course from scratch."],
              ["CS 310 Computer Networks", "Modified an existing course Objectives changed", "2022", "College level 18 May 2022", "Rewrote the objectives."]]]
    monkeypatch.setattr(local_read, "tables", lambda data, max_pages=40: table)
    doc = RR.curriculum(b"x")
    assert [(r.course_code, r.course_title, r.approval_level, r.approval_date) for r in doc.rows] == [
        ("CS 415", "Deep Learning", "University level", "12 May 2021"), ("CS 310", "Computer Networks", "College level", "18 May 2022")]
    drafts = E.read_entries(E.KINDS["curriculum"], "c.pdf", b"x", CTX)
    assert len(drafts) == 2 and drafts[0].route == "text"
    assert drafts[0].values["type_code"] == "new_course" and drafts[1].values["type_code"] == "modified_course"


def test_papers_are_read_without_a_model(monkeypatch):
    feed(monkeypatch, PAPER)
    d = E.read_entries(E.KINDS["paper"], "p.pdf", b"x", CTX)[0]
    assert d.route in ("ocr", "text") and d.values["title"].startswith("Communication-Efficient")


def test_the_rule_modules_can_be_imported_in_any_order():
    for first in ("rule_docs", "rule_text", "rule_letters"):
        code = f"import promoflow.extraction.{first}; from promoflow.extraction import rule_letters as R; assert len(R.RULES) >= 24 and 'funded' in R.NEEDS_APPLICANT"
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-400:]


US_PATENT = """United States Patent
(54) Method for Detecting Anomalous Traffic in Software-Defined Networks
(75) Inventors: Nadia Karimi, Sharjah (AE); Thomas Okonkwo, Beirut (LB)
(73) Assignee: University of Sharjah
Patent No.: US 11,234,567 B2
Date of Patent: Jun. 14, 2022
United States Patent and Trademark Office"""

UAE_PATENT = """United Arab Emirates Ministry of Economy
PATENT CERTIFICATE
Patent No. AE 2345
Title: Adaptive Congestion Control Device for Wireless Mesh Networks
Inventors: Nadia Karimi; Amal Rahmani
Granted on 3 March 2021"""

EXHIBITION = """CERTIFICATE OF PARTICIPATION
This is to certify that Dr. Nadia Karimi exhibited the work "Signal Garden: seven interactive installations" at the Sharjah Biennial Gallery
from 5 to 12 March 2023, organised by Sharjah Art Foundation. The work was approved as creative work by the Arts Committee."""

PROGRAMME = """Programme
"Echoes of the Gulf" - an evening of original compositions
Performed at the Al Majaz Theatre, Sharjah, on 12 November 2022
Presented by the College of Fine Arts, University of Sharjah."""


def test_a_patent_certificate_in_the_us_and_the_uae_layouts():
    us = R.RULES["patent"](US_PATENT)
    assert (us["title"], us["patent_number"], us["office"], us["status"], us["grant_date"]) == (
        "Method for Detecting Anomalous Traffic in Software-Defined Networks", "US 11,234,567 B2", "United States Patent and Trademark Office", "granted", "14 Jun 2022")
    assert us["inventors"] == ["Nadia Karimi", "Thomas Okonkwo"] and R.missing("patent", us) == []
    uae = R.RULES["patent"](UAE_PATENT)
    assert (uae["title"], uae["patent_number"], uae["office"], uae["grant_date"], uae["inventors"]) == (
        "Adaptive Congestion Control Device for Wireless Mesh Networks", "AE 2345", "Ministry of Economy", "3 March 2021", ["Nadia Karimi", "Amal Rahmani"])


def test_a_creative_work_from_an_exhibition_certificate_and_a_performance_programme():
    e = R.RULES["creative"](EXHIBITION)
    assert (e["title"], e["form"], e["venue"], e["organizing_institution"], e["date_from"], e["date_to"], e["approved"]) == (
        "Signal Garden: seven interactive installations", "exhibition", "Sharjah Biennial Gallery", "Sharjah Art Foundation", "5 March 2023", "12 March 2023", True)
    p = R.RULES["creative"](PROGRAMME)
    assert (p["title"], p["form"], p["venue"], p["date_from"], p["date_to"], p["approved"]) == (
        "Echoes of the Gulf", "performance", "Al Majaz Theatre, Sharjah", "12 November 2022", None, None)       # approval is not stated: the applicant says so
    assert p["organizing_institution"] == "College of Fine Arts, University of Sharjah" and R.missing("creative", p) == []


def test_patents_and_creative_works_are_read_without_a_model(monkeypatch):
    feed(monkeypatch, US_PATENT, "text")
    d = E.read_entries(E.KINDS["patent"], "p.pdf", b"x", CTX)[0]
    assert d.route == "text" and d.ok and d.values["office_code"] == "uspto" and d.values["status"] == "granted"
    assert str(d.values["grant_date"]) == "2022-06-14" and d.values["inventors"] == "Nadia Karimi, Thomas Okonkwo"
    feed(monkeypatch, PROGRAMME)
    d = E.read_entries(E.KINDS["creative"], "c.pdf", b"x", CTX)[0]
    assert not d.ok and d.values["form_code"] == "performance" and "state whether this work was approved as creative work" in d.issues
