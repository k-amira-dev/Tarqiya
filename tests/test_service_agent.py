"""The Service Agent with a fake language model: item sources, the shared community evidence, and the checks."""
import json
from datetime import date

from sqlalchemy import select

from promoflow.db.enums import Confidence, FlagSeverity, OrgLevel, Verdict, WorkshopRole
from promoflow.db.models import (
    AdministrativePosition, CommitteeMembership, CommunityActivity, LookupValue, PolicyContribution, RubricScore,
    TrainingDelivered, WorkshopDelivered,
)
from promoflow.workflow.nodes.service import assess, build_context
from promoflow.workflow.persist import save_output
from promoflow.workflow.rubric import ItemJudgment, Judgment
from tests.test_eligibility_checker import make_case
from tests.test_teaching_agent import FakeLLM, payload


def lk(s, list_code, code) -> int:
    return s.scalar(select(LookupValue.id).where(LookupValue.list_code == list_code, LookupValue.code == code))


# Fill a case with committees, an administrative position, a policy contribution, a training, a workshop and
# community activities.
def add_service(s, case_id, *, committees=3, rich=True, community=2):
    for n in range(committees):
        s.add(CommitteeMembership(
            case_id=case_id, committee_name=f"Committee {n}", level=[OrgLevel.DEPARTMENT, OrgLevel.COLLEGE,
                                                                     OrgLevel.UNIVERSITY][n % 3],
            role_id=lk(s, "committee_role", "chair" if n == 0 else "member"), date_from=date(2022, 9, 1),
            date_to=None, contribution_summary="Drafted the annual report."))
    if rich:
        s.add(AdministrativePosition(case_id=case_id, position_id=lk(s, "admin_position", "program_coordinator"),
                                     unit="CS programme", date_from=date(2023, 9, 1), date_to=None))
        s.add(PolicyContribution(case_id=case_id, policy_name="Assessment policy", level=OrgLevel.COLLEGE,
                                 role_id=lk(s, "policy_role", "drafted"), activity_date=date(2024, 3, 1)))
        s.add(TrainingDelivered(case_id=case_id, title="Python for staff", inside_university=True,
                                host_organisation="Teaching centre", activity_date=date(2024, 5, 1), hours=6,
                                participants=25))
        s.add(WorkshopDelivered(case_id=case_id, title="Research methods", organized_by=OrgLevel.COLLEGE,
                                role=WorkshopRole.LECTURER, activity_date=date(2024, 11, 1), attendees=40))
    types = ["school", "funded_company", "media_tv"]
    for n in range(community):
        s.add(CommunityActivity(
            case_id=case_id, activity_type_id=lk(s, "community_activity_type", types[n % 3]), title=f"Activity {n}",
            beneficiary_organisation="A school", applicant_role="Lead", date_from=date(2024, 1, 1),
            date_to=date(2024, 6, 1), beneficiaries=100, deliverables="Delivered a series of sessions.",
            measurable_outcome="Positive feedback."))
    s.flush()


def context(app_env, **kw):
    with app_env.session_scope() as s:
        case_id = make_case(s)
        add_service(s, case_id, **kw)
        s.flush()
        return case_id, build_context(s, case_id)


# Build a model answer for every item: the points chosen by `points`, citing the item's own first record or else a
# shared community activity.
def respond(messages, points=lambda item: item["allowed_points"][1], cite=True):
    """Answer every item: the points chosen by `points`, citing the item's own first record or else a shared one."""
    p = payload(messages)
    shared = p.get("shared_evidence", {}).get("records", [])
    items = []
    for i in p["items"]:
        pool = [r["handle"] for r in i["evidence"]] or [r["handle"] for r in shared]
        pts = points(i)
        items.append(ItemJudgment(item_no=i["item_no"], points=pts, rationale="Clear, substantive contribution.",
                                  cited=pool[:1] if cite and pts > 0 and pool else [], confidence=Confidence.HIGH))
    return Judgment(items=items)


def points(out) -> dict[int, float]:
    return {l.item_no: l.suggested_points for l in out.rubric}


def test_every_item_is_scored_and_the_total_is_capped_at_ten(app_env):
    _, ctx = context(app_env)
    llm = FakeLLM(lambda n, m: respond(m))
    out = assess(ctx, llm)
    assert points(out) == {1: 6, 2: 2, 3: 2, 4: 2, 5: 2} and len(llm.calls) == 1
    assert next(c for c in out.criteria if c.key == "service_total").actual == 10        # 14 capped at 10
    assert out.verdict == Verdict.PASS and "total_capped" in {f.code for f in out.flags}
    assert not out.is_stub and out.prompt_version == "service-v2"


def test_item_one_collects_committees_administrative_positions_and_policy_work(app_env):
    _, ctx = context(app_env)
    llm = FakeLLM(lambda n, m: respond(m))
    assess(ctx, llm)
    item1 = next(i for i in payload(llm.calls[0])["items"] if i["item_no"] == 1)
    handles = {r["handle"].split("-")[0] for r in item1["evidence"]}
    assert handles == {"cm", "ap", "pc"}
    assert item1["summary"]["committees"] == 3 and item1["summary"]["chair_roles"] == 1


def test_community_activities_are_offered_to_items_2_to_5_as_shared_evidence(app_env):
    _, ctx = context(app_env)
    llm = FakeLLM(lambda n, m: respond(m))
    assess(ctx, llm)
    shared = payload(llm.calls[0])["shared_evidence"]
    assert shared["usable_for_items"] == [2, 3, 4, 5] and {r["handle"][:2] for r in shared["records"]} == {"ca"}


def test_one_activity_cited_under_two_items_is_flagged(app_env):
    _, ctx = context(app_env, rich=False, community=1)

    def respond_both(n, messages):
        shared = payload(messages)["shared_evidence"]["records"][0]["handle"]
        return Judgment(items=[ItemJudgment(item_no=i["item_no"], points=i["allowed_points"][1], rationale="Fits.",
                                            cited=[shared], confidence=Confidence.HIGH)
                               for i in payload(messages)["items"] if i["item_no"] in (2, 5)] +
                        [ItemJudgment(item_no=1, points=5, rationale="Committees.", cited=[
                            r["handle"] for r in payload(messages)["items"][0]["evidence"]][:1],
                                      confidence=Confidence.HIGH)])

    out = assess(ctx, FakeLLM(respond_both))
    assert "double_counted" in {f.code for f in out.flags}


def test_nothing_applies_is_a_valid_answer_with_no_citation(app_env):
    _, ctx = context(app_env)
    out = assess(ctx, FakeLLM(lambda n, m: respond(m, points=lambda i: 0 if i["item_no"] == 2 else
                                                   i["allowed_points"][1])))
    assert points(out)[2] == 0
    assert "unverified_claim" not in {f.code for f in out.flags}
    assert out.verdict == Verdict.PASS


def test_a_missing_optional_activity_is_information_not_a_warning(app_env):
    _, ctx = context(app_env, rich=False, community=0)
    llm = FakeLLM(lambda n, m: respond(m))
    out = assess(ctx, llm)
    assert [i["item_no"] for i in payload(llm.calls[0])["items"]] == [1]       # only item 1 has evidence
    missing = [f for f in out.flags if f.code.startswith("no_evidence_item_")]
    assert {f.code for f in missing} == {f"no_evidence_item_{n}" for n in (2, 3, 4, 5)}
    assert all(f.severity == FlagSeverity.INFO for f in missing)
    assert points(out)[1] == 6 and points(out)[2] == 0


def test_no_committee_is_flagged_and_fails_the_presence_check(app_env):
    _, ctx = context(app_env, committees=0, rich=False, community=0)
    out = assess(ctx, FakeLLM(lambda n, m: respond(m)))
    row = next(c for c in out.criteria if c.key == "committees_served")
    assert row.passed is False and row.actual == 0
    assert next(f for f in out.flags if f.code == "no_evidence_item_1").severity == FlagSeverity.WARNING


def test_a_low_total_fails_against_the_pass_mark_from_the_rubric(app_env):
    _, ctx = context(app_env)
    out = assess(ctx, FakeLLM(lambda n, m: respond(m, points=lambda i: i["allowed_points"][0] or 0)))
    total = next(c for c in out.criteria if c.key == "service_total")
    assert total.required in (7, 8) and total.actual == 4 and total.passed is False   # item 1 floor 4, others 0
    assert out.verdict == Verdict.FAIL


def test_a_bad_citation_is_retried_then_marked_unverified(app_env):
    _, ctx = context(app_env)
    llm = FakeLLM(lambda n, m: Judgment(items=[
        ItemJudgment(item_no=i["item_no"], points=i["allowed_points"][1], rationale="Good.", cited=["cm-99999"],
                     confidence=Confidence.HIGH) for i in payload(m)["items"]]))
    out = assess(ctx, llm)
    assert len(llm.calls) == 2 and out.verdict == Verdict.NEEDS_HUMAN
    assert "unverified_claim" in {f.code for f in out.flags}


def test_an_unavailable_model_is_reported_not_guessed(app_env):
    _, ctx = context(app_env)
    out = assess(ctx, None)
    assert out.verdict == Verdict.INCOMPLETE and "llm_unavailable" in {f.code for f in out.flags}


def test_suggestions_are_saved_for_the_service_rubric(app_env):
    case_id, ctx = context(app_env)
    out = assess(ctx, FakeLLM(lambda n, m: respond(m)))
    out.claims = []          # the claim table needs PostgreSQL arrays; it is not part of the SQLite test database
    with app_env.session_scope() as s:
        save_output(s, case_id, out)
    with app_env.session_scope() as s:
        rows = list(s.scalars(select(RubricScore).where(RubricScore.case_id == case_id)))
    assert len(rows) == 5 and sum(float(r.suggested_points) for r in rows) == 14


def test_no_message_to_the_model_carries_a_person_name(app_env):
    _, ctx = context(app_env)
    llm = FakeLLM(lambda n, m: respond(m))
    assess(ctx, llm)
    sent = json.dumps(llm.calls)
    assert "Test Applicant" not in sent and "@" not in sent
