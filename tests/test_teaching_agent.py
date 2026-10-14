"""The Teaching Agent with a fake language model: what it sends, what it scores, how it checks itself."""
import json
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import (
    Confidence, CourseLevel, DeliveryMode, DevelopmentDepth, FlagSeverity, GraduateDegree, OrgLevel, PromotionTrack,
    Rank, Semester, SupervisionRole, SupervisionStatus, TeachingRole, Verdict, ActivityFormat,
)
from promoflow.db.models import (
    AdvisingSemester, CourseFile, CourseTaught, CurriculumContribution, LookupValue, PeerObservation, RubricScore,
    StudentSatisfaction, Supervision, TeachingDevelopment, TeachingInnovation,
)
from promoflow.workflow.nodes import teaching
from promoflow.workflow.nodes.teaching import ItemJudgment, TeachingJudgment, assess, build_context
from promoflow.workflow.persist import save_output
from tests.test_eligibility_checker import make_case

OBSERVER = "Dr. Hidden Observer"
STUDENT = "SECRET STUDENT NAME"
CODES = ["CS101", "CS201", "CS501"]


# Stands in for the language model so the tests need no key, no internet and give the same answer every time. It
# records every call and answers with whatever `respond` returns.
class FakeLLM:
    """Stands in for the language model: records every call and answers with `respond(call_number, messages)`."""

    def __init__(self, respond):
        self.respond, self.calls = respond, []

    def with_structured_output(self, _model):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.respond(len(self.calls), messages)


# Read back the JSON evidence that the agent sent to the (fake) model.
def payload(messages) -> dict:
    return json.loads(messages[1][1].split("\n\nYour previous")[0])


# Build a model answer for every item that was sent: full points, citing the first piece of evidence.
def judgment(messages, points=None, cited=None, confidence=Confidence.HIGH) -> TeachingJudgment:
    return TeachingJudgment(items=[
        ItemJudgment(item_no=i["item_no"], points=i["allowed_points"][1] if points is None else points,
                     rationale="Strong, consistent evidence.", cited=cited or [i["evidence"][0]["handle"]],
                     confidence=confidence) for i in payload(messages)["items"]])


def lk(s, list_code, code) -> int:
    return s.scalar(select(LookupValue.id).where(LookupValue.list_code == list_code, LookupValue.code == code))


# Fill a case with realistic teaching entries. The observer and student names are made-up strings the privacy test
# looks for.
def add_teaching(s, case_id, *, courses=3, files_for=3, rich=True):
    ids = []
    for n, code in enumerate(CODES[:courses]):
        c = CourseTaught(case_id=case_id, academic_year="2025/2026", semester=Semester.FALL, course_code=code,
                         course_title=f"Course {code}", level=CourseLevel.GRADUATE if code == "CS501"
                         else CourseLevel.UNDERGRADUATE, sections=1, students=30, role=TeachingRole.INSTRUCTOR,
                         delivery_mode=DeliveryMode.FACE_TO_FACE)
        s.add(c)
        s.flush()
        ids.append(c.id)
    for cid in ids[:files_for]:
        s.add(CourseFile(case_id=case_id, course_taught_id=cid, is_coordinator=False,
                         kept_in_id=lk(s, "course_file_system", "taskstream"), items=["syllabus"]))
    if not rich:
        return
    for cid in ids:
        s.add(StudentSatisfaction(case_id=case_id, course_taught_id=cid, respondents=30, average_score=4.5,
                                  scale_max=5))
    s.add(PeerObservation(case_id=case_id, course_taught_id=ids[0], observer_role_id=lk(s, "observer_role", "peer"),
                          observer_name=OBSERVER, observation_date=date(2025, 11, 1), rating=85, scale_max=100))
    s.add(CurriculumContribution(case_id=case_id, contribution_type_id=lk(s, "curriculum_contribution_type",
                                                                          "new_course"),
                                 course_or_program="Machine Learning", changes=["textbook", "objectives"],
                                 self_classification=DevelopmentDepth.DEEP, description="Designed a new course.",
                                 approved_by=OrgLevel.COLLEGE, approval_date=date(2025, 5, 1)))
    s.add(TeachingInnovation(case_id=case_id, course_taught_id=ids[0],
                             innovation_type_id=lk(s, "innovation_type", "case_study"),
                             description="Compared two methods.", measured_outcome="Pass rate up 8%."))
    s.add(TeachingInnovation(case_id=case_id, course_taught_id=ids[1],
                             innovation_type_id=lk(s, "innovation_type", "edtech"),
                             description="Interactive quizzes.", measured_outcome=None))
    s.add(AdvisingSemester(case_id=case_id, academic_year="2025/2026", semester=Semester.FALL, advisees=20,
                           meetings_held=40, on_warning_at_start=5, cleared_warning=3, improved_gpa=1))
    s.add(TeachingDevelopment(case_id=case_id, title="Active learning workshop", format=ActivityFormat.WORKSHOP,
                              topic_id=lk(s, "development_topic", "methods"), organizer="Teaching centre",
                              activity_date=date(2025, 10, 1)))
    s.add(Supervision(case_id=case_id, student_name=STUDENT, degree=GraduateDegree.MSC, role=SupervisionRole.MAIN,
                      thesis_title="A thesis", start_date=date(2024, 9, 1), status=SupervisionStatus.IN_PROGRESS))
    s.flush()


# Create a case with teaching evidence and return its id and the agent's evidence context.
def context(app_env, *, full=False, **kw):
    with app_env.session_scope() as s:
        overrides = {"track": PromotionTrack.TO_FULL, "rank_on_appointment": Rank.ASSOCIATE_PROFESSOR} if full else {}
        case_id = make_case(s, **overrides)
        add_teaching(s, case_id, **kw)
        s.flush()
        return case_id, build_context(s, case_id)


def points(out) -> dict[int, float]:
    return {l.item_no: l.suggested_points for l in out.rubric}


def test_full_marks_pass_and_item_5_is_left_out_for_the_associate_track(app_env):
    _, ctx = context(app_env)
    llm = FakeLLM(lambda n, m: judgment(m))
    out = assess(ctx, llm)
    assert points(out) == {1: 4, 2: 4, 3: 2, 4: 3, 6: 5, 7: 2, 8: 4, 9: 4, 10: 2}
    assert out.verdict == Verdict.PASS and len(llm.calls) == 1
    assert next(c for c in out.criteria if c.key == "teaching_total").actual == 30
    assert all(c.verified for c in out.claims) and not out.is_stub and out.prompt_version == "teaching-v1"


def test_the_full_professor_track_scores_item_5_and_caps_the_total(app_env):
    _, ctx = context(app_env, full=True)
    out = assess(ctx, FakeLLM(lambda n, m: judgment(m)))
    assert points(out)[5] == 3
    assert next(c for c in out.criteria if c.key == "teaching_total").actual == 30        # 33 capped at 30
    assert "total_capped" in {f.code for f in out.flags}


def test_no_names_are_ever_sent_to_the_model(app_env):
    _, ctx = context(app_env, full=True)
    llm = FakeLLM(lambda n, m: judgment(m))
    assess(ctx, llm)
    sent = json.dumps(llm.calls)
    assert OBSERVER not in sent and STUDENT not in sent and "A thesis" not in sent
    assert "ss-" in sent and "po-" in sent          # evidence goes under handles


def test_diversity_and_course_files_are_scored_by_rule(app_env):
    _, ctx = context(app_env, courses=2, files_for=1, rich=False)
    out = assess(ctx, FakeLLM(lambda n, m: judgment(m)))
    assert points(out)[3] == 1.0 and points(out)[4] == 2.0      # 2 courses = half; 1 of 2 with files = two thirds


def test_points_outside_the_range_are_clamped_and_flagged(app_env):
    _, ctx = context(app_env)
    out = assess(ctx, FakeLLM(lambda n, m: judgment(m, points=99)))
    assert points(out)[1] == 4 and points(out)[10] == 2
    assert "points_clamped" in {f.code for f in out.flags}


def test_a_bad_citation_gets_one_retry_and_then_passes(app_env):
    _, ctx = context(app_env)

    def respond(n, messages):
        return judgment(messages, cited=["ss-99999"] if n == 1 else None)

    llm = FakeLLM(respond)
    out = assess(ctx, llm)
    assert len(llm.calls) == 2 and "ss-99999" in llm.calls[1][1][1]      # the retry says what was wrong
    assert out.verdict == Verdict.PASS and all(c.verified for c in out.claims)


def test_a_citation_that_stays_bad_is_marked_unverified_for_a_human(app_env):
    _, ctx = context(app_env)
    llm = FakeLLM(lambda n, m: judgment(m, cited=["ss-99999"]))
    out = assess(ctx, llm)
    assert len(llm.calls) == 2                                           # one retry, then stop
    assert out.verdict == Verdict.NEEDS_HUMAN
    assert any(c.verified is False for c in out.claims)
    assert "unverified_claim" in {f.code for f in out.flags}
    assert all(l.confidence == Confidence.LOW for l in out.rubric if l.item_no in teaching.LLM_ITEMS)


def test_no_evidence_means_zero_points_a_flag_and_no_model_call(app_env):
    _, ctx = context(app_env, courses=0, files_for=0, rich=False)
    llm = FakeLLM(lambda n, m: judgment(m))
    out = assess(ctx, llm)
    assert llm.calls == [] and sum(points(out).values()) == 0
    codes = {f.code for f in out.flags}
    assert {"no_evidence_item_1", "no_evidence_item_3", "no_evidence_item_9"} <= codes
    assert out.verdict == Verdict.FAIL and out.model_name is None


@pytest.mark.parametrize("llm", [None, FakeLLM(lambda n, m: (_ for _ in ()).throw(RuntimeError("rate limited")))])
def test_an_unavailable_model_is_reported_not_guessed(app_env, llm):
    _, ctx = context(app_env)
    out = assess(ctx, llm)
    assert out.verdict == Verdict.INCOMPLETE and "llm_unavailable" in {f.code for f in out.flags}
    flag = next(f for f in out.flags if f.code == "llm_unavailable")
    assert flag.severity == FlagSeverity.NEEDS_HUMAN
    assert points(out)[3] == 2 and points(out)[4] == 3                  # the rule items are still scored


def test_suggestions_are_saved_and_a_rerun_clears_the_reviewers_points(app_env):
    case_id, ctx = context(app_env)
    out = assess(ctx, FakeLLM(lambda n, m: judgment(m)))
    out.claims = []          # the claim table needs PostgreSQL arrays; it is not part of the SQLite test database
    with app_env.session_scope() as s:
        save_output(s, case_id, out)
    with app_env.session_scope() as s:
        rows = list(s.scalars(select(RubricScore).where(RubricScore.case_id == case_id)))
        assert len(rows) == len(out.rubric) and all(r.suggested_by_run_id for r in rows)
        rows[0].hod_points = 1
    with app_env.session_scope() as s:
        save_output(s, case_id, out)
    with app_env.session_scope() as s:
        rows = list(s.scalars(select(RubricScore).where(RubricScore.case_id == case_id)))
        assert len(rows) == len(out.rubric) and all(r.hod_points is None for r in rows)
