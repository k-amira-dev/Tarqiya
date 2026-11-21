"""The referee h-index rule (promoflow/rules/referees.py): the referee's h-index must be HIGHER than the one the applicant entered.
Citations do not count. The rule is plain code: same inputs, same answer."""
from promoflow.rules import referees as rules


def candidate(h_index, citations=0):
    return rules.Candidate(key="A1", name="Prof. Test", country="NL", h_index=h_index, citations=citations)


def check(referee_h, applicant_h, referee_citations=0, applicant_citations=10_000):
    c = candidate(referee_h, referee_citations)
    a = rules.ApplicantSide(h_index=applicant_h, citations=applicant_citations)
    return rules.eligibility(c, a, rules.conflicts(c, a, set()))


def test_a_higher_h_index_is_eligible():
    assert check(referee_h=20, applicant_h=12) == (True, [])


def test_an_equal_or_lower_h_index_is_not_eligible():
    ok, reasons = check(referee_h=12, applicant_h=12)
    assert not ok and "not higher than the applicant's 12" in reasons[0]
    assert not check(referee_h=11, applicant_h=12)[0]


def test_citations_are_not_part_of_the_rule():
    assert check(referee_h=20, applicant_h=12, referee_citations=5, applicant_citations=1_000_000) == (True, [])


def test_a_referee_without_an_h_index_is_not_eligible():
    ok, reasons = check(referee_h=None, applicant_h=12)
    assert not ok and "None" in reasons[0]


def test_nothing_to_compare_when_the_applicant_entered_no_h_index():
    assert check(referee_h=3, applicant_h=None) == (True, [])


# ---- the ORCID step of the shortlist (promoflow/workflow/nodes/chancellor.py: orcid_lookup, save) ----

def orcid_stub(titles, emails=()):
    """A fake ORCID API: each ORCID id gets a current job title (None = no job) and, for some, a public email."""
    def get(url, headers=None):
        orcid = url.split("/")[-2]
        if url.endswith("/email"):
            return {"email": [{"email": f"{orcid}@example.org"}] if orcid in emails else []}
        title = titles[orcid]
        return {"affiliation-group": [{"summaries": [{"employment-summary": {"role-title": title, "end-date": None}}]}] if title else []}
    return get


def ranked_rows(orcids, scores=None, basis=None, topics=None):
    from promoflow.db.enums import DecisionBasis
    from promoflow.workflow import scholarly
    return [(scholarly.AuthorProfile(source="openalex", external_id=f"A{i}", name=f"Person {i}", h_index=20, citations=500, works=40,
                                     topics=(topics or {}).get(i, []), institutions=[{"id": "I1", "name": "Some University", "country": "NL"}],
                                     orcid=orcid),
             (scores or {}).get(i, 0.9), "fits", basis or DecisionBasis.RULE) for i, orcid in enumerate(orcids, 1)]


def test_an_english_title_that_is_not_full_professor_is_dropped_and_unknowns_stay():
    from promoflow.db.enums import Rank
    from promoflow.workflow.nodes import chancellor
    titles = {"0000-0000-0000-0001": "Professor", "0000-0000-0000-0002": "Associate Professor", "0000-0000-0000-0003": "Senior Lecturer",
              "0000-0000-0000-0004": None}
    plan = chancellor.Plan(ranked=ranked_rows([*titles, None]))      # the fifth candidate has no ORCID at all
    chancellor.orcid_lookup(plan, min_reports=3, get=orcid_stub(titles))
    assert [row[0].external_id for row in plan.ranked] == ["A1", "A4", "A5"]       # no email needed, no title needed
    assert chancellor.orcid_rank(plan.orcid["A1"]) == Rank.PROFESSOR
    codes = {f.code: f.message for f in plan.flags}
    assert "2 candidate(s) have a current ORCID job title that is not Full Professor" in codes["no_rank_dropped"]
    assert "2 candidate(s) have no job title in ORCID" in codes["rank_unknown"]
    assert "verify_referee_ranks" in codes and "too_few_candidates_after_orcid" not in codes


def test_the_list_is_cut_to_ten_only_after_the_orcid_check():
    from promoflow.workflow.nodes import chancellor
    orcids = [f"0000-0000-0000-{i:04d}" for i in range(1, 16)]
    titles = {o: ("Associate Professor" if i <= 5 else "Professor") for i, o in enumerate(orcids, 1)}   # the 5 best matches are Associates
    plan = chancellor.Plan(ranked=ranked_rows(orcids))
    chancellor.orcid_lookup(plan, min_reports=3, get=orcid_stub(titles))
    assert [row[0].external_id for row in plan.ranked] == [f"A{i}" for i in range(6, 16)]      # ten Professors, not five


def test_the_ranking_is_tried_again_after_one_model_failure():
    from promoflow.workflow.nodes import chancellor

    class FlakyModel:
        """Fails on its first call, like the intermittent BadRequestError seen on the real model, then answers."""
        calls = 0

        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            FlakyModel.calls += 1
            if FlakyModel.calls == 1:
                raise ValueError("the model failed once")
            return chancellor.Ranking(items=[chancellor.Ranked(handle="c-1", score=0.8, rationale="Writes on the same topic.")])

    ctx = chancellor.ShortlistContext(case_id=1, track="to_full", topic_terms=["media"], paper_titles=["A paper"], applicant_ref=None,
                                      applicant=rules.ApplicantSide(h_index=5), recently_used=set(), min_reports=3)
    prof = ranked_rows([None])[0][0]
    plan = chancellor.plan(ctx, [prof], FlakyModel())
    assert FlakyModel.calls == 2 and plan.ranked[0][1] == 0.8
    assert not [f for f in plan.flags if f.code in ("llm_unavailable", "ranking_not_done")]


def test_a_candidate_outside_the_applicants_field_is_never_shortlisted_even_if_a_confirmed_professor():
    from promoflow.db.enums import DecisionBasis
    from promoflow.workflow.nodes import chancellor
    orcids = [f"0000-0000-0000-{i:04d}" for i in range(1, 5)]
    titles = {o: "Professor" for o in orcids}                                       # all four are confirmed Full Professors
    plan = chancellor.Plan(ranked=ranked_rows(orcids, scores={1: 0.0, 2: 0.7, 3: 0.39, 4: 0.5}, basis=DecisionBasis.LLM))
    chancellor.orcid_lookup(plan, min_reports=2, get=orcid_stub(titles))
    assert [row[0].external_id for row in plan.ranked] == ["A2", "A4"]               # 0.0 and 0.39 are below the floor
    assert "2 candidate(s) did not match the applicant's field" in {f.code: f.message for f in plan.flags}["low_fit_dropped"]


def test_without_the_model_candidates_are_scored_by_shared_topic_words():
    from promoflow.workflow.nodes import chancellor

    class DownModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            raise ValueError("the model is down")

    ctx = chancellor.ShortlistContext(case_id=1, track="to_full", topic_terms=["digital journalism", "social media"], paper_titles=["A paper"],
                                      applicant_ref=None, applicant=rules.ApplicantSide(h_index=5), recently_used=set(), min_reports=3)
    rows = ranked_rows([None, None], topics={1: ["Journalism and Media Studies", "Social Media and Politics"],
                                             2: ["Luminescence and Fluorescent Materials"]})
    plan = chancellor.plan(ctx, [rows[0][0], rows[1][0]], DownModel())
    scores = {row[0].external_id: row[1] for row in plan.ranked}
    assert scores["A1"] > chancellor.MIN_FIT_OVERLAP and scores["A2"] == 0.0
    chancellor.orcid_lookup(plan, min_reports=1, get=orcid_stub({}))
    assert [row[0].external_id for row in plan.ranked] == ["A1"]                     # the chemist is dropped even with no model


def test_candidates_confirmed_as_full_professor_come_first_before_the_cut():
    from promoflow.workflow.nodes import chancellor
    orcids = [f"0000-0000-0000-{i:04d}" for i in range(1, 13)]
    titles = {o: ("Professor" if i in (9, 11, 12) else None) for i, o in enumerate(orcids, 1)}     # only 3 are confirmed, and they rank low
    plan = chancellor.Plan(ranked=ranked_rows(orcids))
    chancellor.orcid_lookup(plan, min_reports=3, get=orcid_stub(titles))
    ids = [row[0].external_id for row in plan.ranked]
    assert ids[:3] == ["A9", "A11", "A12"]                         # confirmed first, in their own match order
    assert ids[3:] == [f"A{i}" for i in range(1, 8)] and len(ids) == 10     # then the best matches among the unknowns


def test_a_candidate_without_orcid_is_saved_for_a_person_to_verify(app_env):
    from sqlalchemy import select
    from promoflow.db.models import PromotionCase, Referee
    from promoflow.workflow.nodes import chancellor
    from promoflow.workflow.schemas import FlagOut  # noqa: F401  (imported to make sure the schema module loads)
    from tests.test_extraction_entry_docs import make_case
    uid = make_case(app_env)
    with app_env.session_scope() as s:
        case_id = s.scalar(select(PromotionCase.id).where(PromotionCase.applicant_id == uid))
        ctx = chancellor.ShortlistContext(case_id=case_id, track="to_full", topic_terms=[], paper_titles=[], applicant_ref=None,
                                          applicant=rules.ApplicantSide(), recently_used=set(), min_reports=3)
        plan = chancellor.Plan(ranked=ranked_rows([None]), searched=1)
        shortlist, _ = chancellor.save(s, ctx, plan)
        ref = s.scalar(select(Referee).where(Referee.openalex_author_id == "A1"))
        assert (ref.rank, ref.email, ref.rank_verified) == (None, None, False)
    assert shortlist[0]["orcid_title"] is None and shortlist[0]["orcid_says_full_professor"] is False
