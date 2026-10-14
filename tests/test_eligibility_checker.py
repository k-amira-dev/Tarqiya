"""The real Eligibility Checker (promoflow/workflow/nodes/eligibility.py) on small hand-built cases."""
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from promoflow.db.enums import DegreeLevel, FlagSeverity, PromotionTrack, Rank, Verdict
from promoflow.db.models import CaseDocument, CriterionResult, Degree, Flag, PromotionCase, RankHistory, ScopusEvidence, User
from promoflow.dossier import section0 as s0
from promoflow.rules.eligibility import years_between
from promoflow.workflow.nodes import eligibility as elig
from promoflow.workflow.persist import save_output

ON = date(2026, 10, 3)  # inside the 1-7 October window
S0_VALUES = {
    "academic_year": "2026/2027", "track": PromotionTrack.TO_ASSOCIATE, "specialization": "Computer Science",
    "fine_specialization": "Machine Learning", "research_keywords": [],
    "appointment_date": date(2019, 9, 1), "rank_on_appointment": Rank.ASSISTANT_PROFESSOR,
    "current_rank_date": date(2019, 9, 1), "scopus_author_id": "57193456789", "orcid": None,
    "phd_outside_uae": False, "early_application": False, "exceptional_case": False,
    "exceptional_justification": None, "previously_rejected": False, "rejection_date": None,
}


def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


def make_case(s, **overrides) -> int:
    return s0.save(s, applicant(s).id, {**S0_VALUES, **overrides}, ON)


def fill(s, case_id, *, skip_doc=None, scopus_date=date(2026, 9, 20), rank_date=date(2019, 9, 1)):
    """Everything the checker looks for besides Section 0: documents, rank history, a PhD and Scopus evidence."""
    uid = applicant(s).id
    for code, kind, slot, *_ in elig.REQUIRED_DOCUMENTS:
        if code != skip_doc:
            s.add(CaseDocument(case_id=case_id, section_code=code, kind=kind, slot=slot, original_filename="x.pdf",
                               stored_path="x", mime_type="application/pdf", size_bytes=10, sha256="0" * 64,
                               uploaded_by=uid))
    s.add(RankHistory(case_id=case_id, rank=Rank.ASSISTANT_PROFESSOR, date_obtained=rank_date, university="Univ",
                      country_code="AE", held_from=rank_date, held_to=None, at_this_university=True))
    s.add(Degree(case_id=case_id, level=DegreeLevel.PHD, specialization="CS", university="Univ", country_code="AE",
                 study_from=date(2012, 9, 1), graduation_date=date(2016, 6, 1)))
    if scopus_date:
        s.add(ScopusEvidence(case_id=case_id, h_index=5, total_citations=100, screenshot_date=scopus_date))
    s.flush()


def check(app_env, *, fill_kwargs=None, submitted=None, **s0_overrides):
    with app_env.session_scope() as s:
        case_id = make_case(s, **s0_overrides)
        fill(s, case_id, **(fill_kwargs or {}))
        if submitted:
            s.get(PromotionCase, case_id).submitted_at = submitted
        s.flush()
        return elig.check_case(s, case_id, ON)


def codes(out):
    return {f.code for f in out.flags}


def test_years_between_counts_whole_calendar_years():
    assert years_between(date(2021, 10, 3), date(2026, 10, 3)) == 5.0          # one leap day in between
    assert years_between(date(2019, 10, 3), date(2024, 10, 3)) == 5.0          # two leap days
    assert years_between(date(2021, 10, 4), date(2026, 10, 3)) < 5.0           # one day short
    # a 29 February start counts its anniversary on 28 February in a non-leap year
    assert years_between(date(2020, 2, 29), date(2025, 2, 28)) == 5.0
    assert years_between(date(2020, 2, 29), date(2025, 2, 27)) < 5.0


def test_complete_dossier_passes_with_no_flags(app_env):
    out = check(app_env)
    assert out.verdict == Verdict.PASS and out.flags == []
    assert not out.is_stub and out.model_name is None


def test_missing_signed_form_is_incomplete_with_guidance(app_env):
    out = check(app_env, fill_kwargs={"skip_doc": "1"})
    assert out.verdict == Verdict.INCOMPLETE
    msg = next(f.message for f in out.flags if f.code == "document_missing")
    assert "Signed application form is missing" in msg and "Section 1" in msg


def test_empty_dossier_lists_every_gap(app_env):
    with app_env.session_scope() as s:
        case_id = make_case(s)
        out = elig.check_case(s, case_id, ON)
    assert out.verdict == Verdict.INCOMPLETE
    assert sum(1 for f in out.flags if f.code == "document_missing") == len(elig.REQUIRED_DOCUMENTS)
    assert {"eligibility_rank_history", "eligibility_doctorate_degree", "eligibility_scopus_evidence"} <= codes(out)


def test_time_in_rank_exactly_five_years_passes(app_env):
    out = check(app_env, current_rank_date=date(2021, 10, 3), fill_kwargs={"rank_date": date(2021, 10, 3)})
    assert out.verdict == Verdict.PASS


def test_time_in_rank_one_day_short_fails(app_env):
    out = check(app_env, current_rank_date=date(2021, 10, 4), fill_kwargs={"rank_date": date(2021, 10, 4)})
    assert out.verdict == Verdict.FAIL
    msg = next(f.message for f in out.flags if f.code == "eligibility_time_in_current_rank")
    assert "minimum is 5" in msg and "p.13" in msg          # fixed guidance quoting the policy page
    row = next(c for c in out.criteria if c.key == "time_in_current_rank")
    assert row.required == 5.0 and row.actual < 5.0 and row.passed is False


def test_exceptional_case_is_left_to_the_hod(app_env):
    out = check(app_env, current_rank_date=date(2022, 10, 3), fill_kwargs={"rank_date": date(2022, 10, 3)},
                exceptional_case=True, exceptional_justification="Exceptional research volume.")
    assert out.verdict == Verdict.NEEDS_HUMAN
    flag = next(f for f in out.flags if f.code == "exceptional_case")
    assert flag.severity == FlagSeverity.NEEDS_HUMAN


def test_rank_date_mismatch_between_section_0_and_4_needs_a_human(app_env):
    out = check(app_env, fill_kwargs={"rank_date": date(2019, 10, 1)})
    assert out.verdict == Verdict.NEEDS_HUMAN and "rank_date_mismatch" in codes(out)


def test_old_scopus_screenshot_is_incomplete(app_env):
    out = check(app_env, fill_kwargs={"scopus_date": ON.replace(month=8, day=19)})   # 45 days old
    assert out.verdict == Verdict.INCOMPLETE
    assert "45 days" in next(f.message for f in out.flags if f.code == "eligibility_scopus_screenshot_recent")


def test_submission_must_fall_inside_a_window(app_env):
    with app_env.session_scope() as s:
        case_id = make_case(s)
        fill(s, case_id)
        case = s.get(PromotionCase, case_id)
        case.submitted_at = datetime(2026, 9, 25, 10, tzinfo=timezone.utc)      # not a submission window
        late = elig.check_case(s, case_id, ON)
        case.submitted_at = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)      # inside 1-7 October
        ok = elig.check_case(s, case_id, ON)
    assert late.verdict == Verdict.FAIL and "eligibility_submission_window" in codes(late)
    assert ok.verdict == Verdict.PASS


def test_output_is_saved_to_the_result_tables(app_env):
    with app_env.session_scope() as s:
        case_id = make_case(s)
        out = elig.check_case(s, case_id, ON)
        save_output(s, case_id, out)
    with app_env.session_scope() as s:
        assert s.scalar(select(func.count()).select_from(CriterionResult)) == len(out.criteria)
        assert s.scalar(select(func.count()).select_from(Flag)) == len(out.flags)
