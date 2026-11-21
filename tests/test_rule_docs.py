"""Degrees, rank decisions, awards, thesis supervision, teaching innovation reports and policy documents read by plain rules (no model).
The texts are real OCR output (or text layers) from the pilot dossiers, OCR slips included."""
from promoflow.extraction import entry_docs as E, rule_docs as RD, rule_letters as R
from tests.test_rule_letters import CTX, feed

DEGREE = """NORTHFIELD
INSTITUTE OF
TECHNOLOGY
EST.
OFFICIAL SEAV
NORTHFIELD INSTITUTE OF TECHNOLOGY
Canada
CERTIFICATE OF MASTER OF
SCIENCE
The Senate of the University, on the recommendation of the Faculty,
hereby confers upon
NADIA KARIMI
the degree of
Master of Science
in
Computer Science (Networking)
Thesis: Adaptive Congestion Control for Wireless Mesh Networks
Conferred on 20 July 2010
Certificate No. NIT/MS/2010/2290"""

RANK = """Kuwait
Gulf Coast University
Human Resources / Faculty Affairs
Decision No.: GCU/HR/2018/011 Date: 20 December 2017
Article 1. Dr. Nadia Karimi is appointed to the academic rank of Lecturer at Gulf Coast University, in the
Department of Computer Science, with effect from 01 January 2018."""

AWARD = """INTERNATIONAL CONFERENCE ON INTELLIGENT NETWORKS
ANDSECURITY (ICINS 2022)
BEST PAPER AWARD
is proudly presented to
Dr. Nadia Karimi
for the paper "Lightweight Federated Anomaly Detection on Edge
Gateways", selected among 84 accepted papers.
Awarded on the 2oth of November 2022"""

DEFENCE = """University of Sharjah
Examination Committee Decision
CANDIDATE
PROGRAMME
Zayed Al-Falasi
Master of Science in Computer Science
ID G20231069
DATE OF DEFENCE
STUDIES BEGAN
13/06/2023
01September 2021
THESIS TITLE
Explainable intrusion detection for loT networks
Examination committee
Name
Affiliation
Role
Dr. Nadia Karimi
University of Sharjah
Supervisor (Chair)
Dr. Samer Khoury
University of Sharjah
Internal examiner
Decision
The committee, having read the thesis and examined the candidate, decided: PAss with minor
revisions. Revisions to be approved by the Chair within 30 days. Degree to be conferred at the next
graduation ceremony (01 August 2023)."""

PROPOSAL = """S IMU LATE D - FOR T EST IN G
University of Sharjah Form GS-3
STUDENT
Rami Al-Hammadi (ID G20193919)
PROGRAMME
Master of Science in Computer Science
SUPERVISOR
Dr. Nadia Karimi
PROPOSAL APPROVED
15.12.2024
WORKING TITLE
Multi-agent coordination in software-defined networks
The Graduate Studies Committee approved the thesis proposal. Studies began on 01/09/2024; the student is in good standing."""

INNOVATION = """University of Sharjah
Teaching Innovation Report
Al-assisted code feedback in Programming Fundamentals
INSTRUCTOR
COURSE / TERM
CS 110, Spring 2024 (CRN10667; 31 students
What was done
Students submitted weekly programming exercises. An approved coding assistant produced first-level feedback.
Measured outcome
Before the pilot, feedback took seven days. During the pilot the turnaround was two days and 71% of students revised.
Indicator
Before"""

POLICY_SCAN = """University of Sharjah
Policy document
University Regulations for Student Programming Competitions
Version 1.0 | Approved by: University Council | Effective: 08 Dec 2021
Drafting and review committee
Member
Role in the committee
Prof. Karim Al-Masri
Member
Dr. Nadia Karimi
Drafting member"""

POLICY_TEXT = """University of Sharjah Policy document
Department Policy on the Use of Generative AI in Coursework
Version 1.0 | Approved by: Department Council of Computer Science | Effective: 05 Jun 2024
Member Role in the committee
Dr. Nadia Karimi Chair
Dr. Amal Rahmani Secretary"""

ME = "Dr. Nadia Karimi"


def test_degree_certificate():
    assert RD.degree_cert(DEGREE) == {
        "degree_name": "Master of Science", "field_of_study": "Computer Science (Networking)", "university": "Northfield Institute of Technology",
        "country": "Canada", "conferral_date": "20 July 2010", "thesis_title": "Adaptive Congestion Control for Wireless Mesh Networks"}


def test_rank_decision():
    got = R.RULES["rank"](RANK)
    assert (got["rank_title"], got["institution"], got["country"], got["effective_date"], got["decision_date"]) == (
        "Lecturer", "Gulf Coast University", "Kuwait", "01 January 2018", "20 December 2017")


def test_award_splits_name_from_body_and_fixes_ocr_slips():
    got = R.RULES["award"](AWARD)
    assert got["award_name"] == "Best Paper Award"
    assert got["awarding_body"] == "International Conference on Intelligent Networks and Security (ICINS 2022)"
    assert got["award_date"] == "20th of November 2022"


def test_supervision_defence_form_and_proposal_form():
    d = R.RULES["supervision"](DEFENCE, ME)
    assert (d["student_name"], d["thesis_title"], d["applicant_role"]) == ("Zayed Al-Falasi", "Explainable intrusion detection for IoT networks", "Supervisor (Chair)")
    assert (d["defence_date"], d["studies_began"], d["conferral_date"]) == ("13/06/2023", "01 September 2021", "01 August 2023")
    assert d["degree"] == "Master of Science in Computer Science"
    p = R.RULES["supervision"](PROPOSAL, ME)
    assert (p["student_name"], p["applicant_role"], p["studies_began"], p["defence_date"]) == ("Rami Al-Hammadi", "Supervisor", "01/09/2024", None)


def test_the_supervision_role_is_the_applicants_own_row():
    assert R.RULES["supervision"](DEFENCE, "Dr. Samer Khoury")["applicant_role"] == "Internal examiner"


def test_innovation_and_policy():
    i = R.RULES["innovation"](INNOVATION)
    assert i["title"] == "AI-assisted code feedback in Programming Fundamentals" and (i["course_code"], i["term"]) == ("CS 110", "Spring 2024")
    assert i["what_was_done"].startswith("Students submitted") and "71%" in i["measured_outcome"]
    scan = R.RULES["policy"](POLICY_SCAN, ME)
    assert (scan["policy_name"], scan["approving_body"], scan["effective_date"], scan["applicant_role"]) == (
        "University Regulations for Student Programming Competitions", "University Council", "08 Dec 2021", "Drafting member")
    text = R.RULES["policy"](POLICY_TEXT, ME)
    assert text["policy_name"].startswith("Department Policy") and text["applicant_role"] == "Chair"


def test_ordinal_dates_keep_their_suffix():
    assert R._date("5th of June 2022") == "5th of June 2022" and R._date("31August 2023") == "31 August 2023"


def test_the_new_kinds_are_read_without_a_model(monkeypatch):
    feed(monkeypatch, DEFENCE)
    d = E.read_entries(E.KINDS["supervision"], "s.pdf", b"x", CTX)[0]
    assert d.route in ("ocr", "text") and d.ok
    assert d.values["student_name"] == "Zayed Al-Falasi" and d.values["role"] == "main" and d.values["status"] == "graduated"
    feed(monkeypatch, DEGREE)
    d = E.read_entries(E.KINDS["degree"], "d.pdf", b"x", CTX)[0]
    assert d.route in ("ocr", "text") and d.values["level"] == "master"
