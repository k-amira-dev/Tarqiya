"""Evidence documents -> entries: the page-picture reader, the rules that turn what was read into entry values, and saving.
Fake models stand in for Groq, so nothing here costs money or needs a key."""
import io
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from promoflow.db.models import CommitteeMembership, Supervision, User, WorkshopDelivered
from promoflow.dossier import doc_entries
from promoflow.dossier import section0 as s0
from promoflow.extraction import doc_llm, entry_docs as E, picture_doc
from tests.test_eligibility_checker import ON, S0_VALUES
from tests.test_extraction_teaching_docs import FakeLLM

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"
CTX = E.Ctx(applicant_name="Dr. Samira Al-Tamimi")


class FakeVision:
    """Looks like the vision model: .invoke(messages) -> a reply with .content and .usage_metadata."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def invoke(self, messages):
        self.calls += 1
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(content=r, usage_metadata={"input_tokens": 2000, "output_tokens": 80})


def blank_pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


# ---- dates -----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("2022-09-01", date(2022, 9, 1)), ("01 September 2022", date(2022, 9, 1)), ("1 September 2022", date(2022, 9, 1)),
    ("14th of November 2022", date(2022, 11, 14)), ("11/06/2022", date(2022, 6, 11)), ("2023-11", date(2023, 11, 1)),
    ("April 2022", date(2022, 4, 1)), ("", None), (None, None), ("sometime", None)])
def test_dates_in_many_written_forms(text, expected):
    assert E.parse_date(text) == expected


# ---- the page-picture reader -----------------------------------------------------------------------------------------

JSON = '{"title": "Active learning", "organiser": "Teaching Centre", "activity_date": "2019-10-23", "hours": 6, "event_type": "workshop"}'


def test_page_images_are_made_from_a_pdf():
    images = picture_doc.page_images(blank_pdf())
    assert len(images) == 1 and images[0][:2] == b"\xff\xd8"                 # a JPEG


def test_the_picture_reader_parses_an_answer_wrapped_in_code_fences():
    parsed, usage = picture_doc.read_picture([b"x"], E.AttendanceCert, FakeVision("Here is the result:\n```json\n" + JSON + "\n```"))
    assert (parsed.title, parsed.hours) == ("Active learning", 6) and usage.input_tokens == 2000


def test_the_picture_reader_retries_then_gives_a_plain_error(monkeypatch):
    monkeypatch.setattr(picture_doc.time, "sleep", lambda s: None)
    parsed, _ = picture_doc.read_picture([b"x"], E.AttendanceCert, FakeVision("not json at all", JSON))
    assert parsed.title == "Active learning"
    with pytest.raises(doc_llm.ReadFailed, match="expected form"):
        picture_doc.read_picture([b"x"], E.AttendanceCert, FakeVision("nothing useful"))


def test_a_used_up_daily_allowance_fails_at_once_and_says_why(monkeypatch):
    slept = []
    monkeypatch.setattr(picture_doc.time, "sleep", lambda s: slept.append(s))
    vision = FakeVision(RuntimeError("RateLimitError 429 ... tokens per day (TPD): Limit 200000 ... try again in 13m52s"))
    with pytest.raises(doc_llm.ReadFailed, match="daily reading allowance"):
        picture_doc.read_picture([b"x"], E.AttendanceCert, vision)
    assert vision.calls == 1 and slept == []                                    # no pointless waiting


def test_a_file_with_text_is_read_as_text_and_a_scan_as_a_picture():
    answer = E.AttendanceCert(title="T", organiser="O", activity_date="2020-01-02", hours=3, event_type=None)
    text_pdf = (FIXTURES / "student_evaluation_b.pdf").read_bytes()
    parsed, _, route = picture_doc.read_entry_file(text_pdf, E.AttendanceCert, FakeLLM(answer), FakeVision(JSON))
    assert route == "text" and parsed is answer
    parsed, _, route = picture_doc.read_entry_file(blank_pdf(), E.AttendanceCert, FakeLLM(answer), FakeVision(JSON))
    assert route == "picture" and parsed.title == "Active learning"
    with pytest.raises(doc_llm.ReadFailed, match="scan"):
        picture_doc.read_entry_file(blank_pdf(), E.AttendanceCert, FakeLLM(answer), None)


# ---- what each kind of document becomes ------------------------------------------------------------------------------

def test_committee_level_comes_from_the_name_or_else_from_who_signed():
    def build(name, signer, role="Member", d_from="2022-09-01", d_to="2024-08-31"):
        return E.build_committee(E.CommitteeLetter(committee_name=name, role=role, date_from=d_from, date_to=d_to, signer_title=signer), CTX)
    v, issues = build("Department Curriculum Committee", "Head, Department of Mass Communication", role="Chair")
    assert (v["level"], v["role_code"], v["date_from"], v["date_to"]) == ("department", "chair", date(2022, 9, 1), date(2024, 8, 31)) and not issues
    assert build("Graduate Studies Committee", "Dean, College of Communication", role="Secretary")[0]["level"] == "college"
    assert build("Digital Learning Group", "Vice President for Academic Affairs")[0]["level"] == "university"
    v, issues = build("Mystery Panel", None, role="observer", d_from=None, d_to=None)
    assert any("level" in i for i in issues) and any("role" in i for i in issues) and any("start date" in i for i in issues)
    assert build("College Research Committee", "Dean", d_to=None)[0]["date_to"] is None                       # open-ended


def test_administrative_positions():
    v, _ = E.build_admin(E.AdminLetter(position_title="Programme Coordinator, BA in Mass Communication", unit="BA in Mass Communication", date_from="2021-09-01", date_to="2023-08-31"), CTX)
    assert v["position_code"] == "program_coordinator" and v["unit"] == "BA in Mass Communication"
    v, _ = E.build_admin(E.AdminLetter(position_title="Deputy Head of Department", unit=None, date_from="2024-09-01", date_to=None), CTX)
    assert v["position_code"] == "other"                                                                       # a deputy is not the Head
    assert E.build_admin(E.AdminLetter(position_title="Head of Department", unit="Mass Communication", date_from="2020-01-01", date_to=None), CTX)[0]["position_code"] == "hod"


def test_workshop_and_training_rules():
    both = E.build_workshop(E.WorkshopCert(title="W", organized_by="College", role="organiser and lecturer", activity_date="2022-02-16", attendees=45), CTX)[0]
    assert both["role"] == "organiser_and_lecturer" and both["attendees"] == 45 and both["organized_by"] == "college"
    assert E.build_workshop(E.WorkshopCert(title="W", organized_by="C", role="both", activity_date="2022-02-16", attendees=None), CTX)[0]["role"] == "organiser_and_lecturer"
    assert E.build_workshop(E.WorkshopCert(title="W", organized_by="C", role="guest of honour", activity_date="2022-02-16", attendees=None), CTX)[1] == ["choose who organised it (department, college or university)", "role not understood"]
    inside = E.build_training(E.TrainingCert(title="T", host_organisation="University of Sharjah Library", hours=4, activity_date="2023-05-18"), CTX)[0]
    outside = E.build_training(E.TrainingCert(title="T", host_organisation="Youth Media Centre", hours=4, activity_date="2023-05-18"), CTX)[0]
    assert (inside["inside_university"], outside["inside_university"], outside["hours"]) == (True, False, 4.0)


def test_community_and_development_mapping():
    v, issues = E.build_community(E.CommunityLetter(organisation="Secondary schools", activity_title="Media literacy workshops for secondary schools", role="Volunteer trainer",
                                                    date_from="2021-10", date_to=None, outputs="8 sessions"), CTX)
    assert (v["activity_type_code"], v["date_from"], v["date_to"]) == ("school", date(2021, 10, 1), date(2021, 10, 1)) and not issues
    assert any("delivered" in i for i in E.build_community(E.CommunityLetter(organisation="O", activity_title="A", role="R", date_from="2021-10", date_to=None, outputs=""), CTX)[1])
    v, _ = E.build_development(E.AttendanceCert(title="Designing rubrics and assessment", organiser="TLC", activity_date="2019-03-14", hours=4, event_type=None), CTX)
    assert (v["format"], v["topic_code"]) == ("workshop", "assessment")
    assert E.build_development(E.AttendanceCert(title="Using AI tools in teaching", organiser="TLC", activity_date="2023-11-08", hours=6, event_type="workshop"), CTX)[0]["topic_code"] == "ai"
    assert E.build_development(E.AttendanceCert(title="Gulf Education Conference", organiser="GAHE", activity_date="2023-11-08", hours=None, event_type=None), CTX)[0]["format"] == "conference"


def test_supervision_status_role_and_degree():
    done = E.build_supervision(E.SupervisionDoc(student_name="S N", thesis_title="T", degree="Master of Arts in Media Studies", applicant_role="Supervisor (Chair)",
                                                studies_began="2020-09-01", defence_date="2022-06-11", conferral_date="2022-08-01", outcome="PASS with minor revisions"), CTX)[0]
    assert (done["degree"], done["role"], done["status"], done["graduation_date"]) == ("msc", "main", "graduated", date(2022, 8, 1))
    open_ = E.build_supervision(E.SupervisionDoc(student_name="S N", thesis_title="T", degree="PhD", applicant_role="Co-supervisor", studies_began="2024-09-01",
                                                 defence_date=None, conferral_date=None, outcome="proposal approved"), CTX)[0]
    assert (open_["degree"], open_["role"], open_["status"], open_["graduation_date"]) == ("phd", "associate", "in_progress", None)
    failed = E.build_supervision(E.SupervisionDoc(student_name="S", thesis_title="T", degree="MSc", applicant_role="supervisor", studies_began="2020-09-01",
                                                  defence_date="2022-06-11", conferral_date=None, outcome="did not pass"), CTX)[0]
    assert failed["status"] == "in_progress"


# ---- saving ----------------------------------------------------------------------------------------------------------

def make_case(app_env) -> int:
    with app_env.session_scope() as s:
        uid = s.scalar(select(User.id).where(User.email == "applicant@promoflow.test"))
        s0.save(s, uid, dict(S0_VALUES), ON)
        return uid


def draft(kind, values, name="evidence.pdf", issues=None):
    return E.EntryDraft(kind, name, b"%PDF-1.4 test", values, issues or [], "picture")


def test_saving_committees_with_evidence_and_no_duplicates(app_env):
    uid = make_case(app_env)
    with app_env.session_scope() as s:
        ctx = doc_entries.load_ctx(s, "Dr. Test")
    assert "chair" in ctx.ids["committee_role"] and ctx.labels["committee_role"]["chair"] == "Chair"
    values = dict(committee_name="Department Curriculum Committee", level="department", role_code="chair", date_from=date(2022, 9, 1), date_to=date(2024, 8, 31), contribution_summary=None)
    other = dict(values, committee_name="College Research Committee", level="college", role_code="member")
    with app_env.session_scope() as s:
        first = doc_entries.add_entries(s, uid, "committee", [draft("committee", dict(values), "a.pdf"), draft("committee", dict(other), "b.pdf")], ctx)
    with app_env.session_scope() as s:
        second = doc_entries.add_entries(s, uid, "committee", [draft("committee", dict(values), "a.pdf")], ctx)
        rows = s.scalars(select(CommitteeMembership)).all()
    assert (first.added, second.added, second.skipped_existing) == (2, 0, 1) and len(rows) == 2


def test_an_entry_that_fails_validation_is_reported_not_saved(app_env):
    uid = make_case(app_env)
    with app_env.session_scope() as s:
        ctx = doc_entries.load_ctx(s)
    bad = dict(title="Workshop", organized_by="college", role="organiser", activity_date=date(2999, 1, 1), attendees=10)        # a date in the future
    good = dict(title="Workshop 2", organized_by="college", role="lecturer", activity_date=date(2023, 3, 22), attendees=None)
    with app_env.session_scope() as s:
        out = doc_entries.add_entries(s, uid, "workshop", [draft("workshop", bad, "bad.pdf"), draft("workshop", good, "good.pdf")], ctx)
        rows = s.scalars(select(WorkshopDelivered)).all()
    assert out.added == 1 and len(out.rejected) == 1 and "future" in out.rejected[0] and rows[0].title == "Workshop 2"


def test_saving_a_supervision_record(app_env):
    uid = make_case(app_env)
    with app_env.session_scope() as s:
        ctx = doc_entries.load_ctx(s)
    values = dict(student_name="Student One", degree="msc", role="main", thesis_title="A thesis", start_date=date(2020, 9, 1), status="graduated", graduation_date=date(2022, 8, 1))
    with app_env.session_scope() as s:
        out = doc_entries.add_entries(s, uid, "supervision", [draft("supervision", values)], ctx)
        row = s.scalars(select(Supervision)).one()
    assert out.added == 1 and (row.thesis_title, row.status.value, row.role.value) == ("A thesis", "graduated", "main")
