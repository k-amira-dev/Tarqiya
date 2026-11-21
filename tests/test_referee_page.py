"""The Chancellor's referee-selection page (promoflow/ui/views/referees.py): the list, the shortlist, verifying a referee's rank and
email, and making a selection (only verified Professors can be picked)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from promoflow.auth.service import create_session
from promoflow.db.enums import CaseStatus, Rank
from promoflow.db.models import AuditLogEntry, PromotionCase, Referee, RefereeCandidate, ScopusEvidence, User
from promoflow.ui.auth import _load
from promoflow.workflow import referee_view
from promoflow.workflow.scholarly import OrcidSuggestion
from tests.test_extraction_entry_docs import make_case


def shortlist(app_env, *, anna_rank=None, anna_verified=False, applicant_h=None):
    uid = make_case(app_env)
    with app_env.session_scope() as s:
        case = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == uid))
        case.status = CaseStatus.REFEREE_SELECTION
        if applicant_h is not None:                      # the h-index the applicant entered in Section 5F
            s.add(ScopusEvidence(case_id=case.id, h_index=applicant_h, total_citations=100, screenshot_date=date.today()))
        ids = []
        for i, (name, uni, cc, score, conflict) in enumerate([("Prof. Anna Berg", "University of Groningen", "NL", "0.912", False),
                                                              ("Prof. Omar Conflict", "Some University", "GB", "0.700", True)], 1):
            first = i == 1
            ref = Referee(full_name=name, university=uni, country_code=cc, rank=anna_rank if first else None,
                          rank_verified=anna_verified if first else False, email="anna.berg@rug.nl" if first and anna_verified else None,
                          orcid="0000-0002-1825-0097" if first else None, h_index=30 + i, citation_count=1000, topics=["Journalism"],
                          openalex_author_id=f"A{i}")
            s.add(ref)
            s.flush()
            cand = RefereeCandidate(case_id=case.id, referee_id=ref.id, match_score=Decimal(score), match_rationale="Writes on digital journalism.",
                                    coi_coauthor=conflict, coi_same_institution=False, coi_used_within_5_years=False, eligible=not conflict)
            s.add(cand)
            s.flush()
            ids.append(cand.id)
        return case.id, ids


def chancellor_token(app_env):
    with app_env.session_scope() as s:
        return create_session(s, s.scalar(select(User).where(User.email == "chancellor@promoflow.test")))


def test_the_data_layer_lists_the_case_and_its_shortlist_best_match_first(app_env):
    case_id, ids = shortlist(app_env)
    with app_env.session_scope() as s:
        assert [c.case_id for c in referee_view.cases(s)] == [case_id]
        rows = referee_view.shortlist(s, case_id)
    assert [r.name for r in rows] == ["Prof. Anna Berg", "Prof. Omar Conflict"]
    assert rows[0].conflicts == [] and rows[1].conflicts == ["has co-authored with the applicant"] and rows[1].eligible is False


def blocked_by_name(app_env, case_id):
    with app_env.session_scope() as s:
        return {r.name: r.blocked for r in referee_view.shortlist(s, case_id)}


def test_an_unverified_referee_and_a_conflict_are_blocked_with_a_reason(app_env):
    case_id, ids = shortlist(app_env)
    blocked = blocked_by_name(app_env, case_id)
    assert blocked["Prof. Anna Berg"] == "A person must verify the rank and email first."
    assert blocked["Prof. Omar Conflict"] == "Conflict of interest."


def test_a_verified_professor_can_be_selected(app_env):
    case_id, ids = shortlist(app_env, anna_rank=Rank.PROFESSOR, anna_verified=True)
    assert blocked_by_name(app_env, case_id)["Prof. Anna Berg"] is None


def test_a_referee_whose_h_index_is_not_higher_than_the_applicants_is_blocked(app_env):
    case_id, ids = shortlist(app_env, anna_rank=Rank.PROFESSOR, anna_verified=True, applicant_h=31)     # Anna's h-index is 31
    assert blocked_by_name(app_env, case_id)["Prof. Anna Berg"] == "The referee's h-index must be higher than the applicant's."


def test_a_referee_with_a_higher_h_index_than_the_applicants_is_not_blocked(app_env):
    case_id, ids = shortlist(app_env, anna_rank=Rank.PROFESSOR, anna_verified=True, applicant_h=30)
    assert blocked_by_name(app_env, case_id)["Prof. Anna Berg"] is None


def test_the_card_shows_the_referees_h_index_next_to_the_one_the_applicant_entered(app_env):
    case_id, ids = shortlist(app_env, applicant_h=12)
    at = open_case(app_env, case_id)
    assert "h-index 31 (applicant entered 12)" in " ".join(m.value for m in at.markdown)


def test_a_verified_associate_professor_is_blocked(app_env):
    case_id, ids = shortlist(app_env, anna_rank=Rank.ASSOCIATE_PROFESSOR, anna_verified=True)
    assert blocked_by_name(app_env, case_id)["Prof. Anna Berg"] == "Verified rank is not Professor."


SCRIPT = """
from promoflow.ui import theme
from promoflow.ui.views import referees
theme.inject()
referees.render()
"""


def fake_selection(monkeypatch):
    """Replace the real selection (it would start the LangGraph run) with one that records the call."""
    from promoflow.workflow import review_service
    calls = []
    monkeypatch.setattr(review_service, "select_referees", lambda case_id, user_id, ids, **kw: calls.append((case_id, user_id, list(ids))))
    return calls


def open_case(app_env, case_id):
    at = AppTest.from_string(SCRIPT, default_timeout=60)
    at.session_state["current_user"] = _load(chancellor_token(app_env))
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.button(key=f"ref_open_{case_id}").click()
    return at.run()


def test_the_chancellor_sees_the_case_and_cannot_tick_an_unverified_or_conflicted_referee(app_env):
    case_id, ids = shortlist(app_env)
    at = open_case(app_env, case_id)
    text = " ".join(m.value for m in at.markdown) + " ".join(c.label for c in at.checkbox)
    assert "Prof. Anna Berg" in text and "Prof. Omar Conflict" in text and "Conflict: has co-authored" in text and "Not verified" in text
    assert at.checkbox(key=f"ref_pick_{ids[0]}").disabled            # nobody verified the rank yet
    assert at.checkbox(key=f"ref_pick_{ids[1]}").disabled            # a conflict of interest


def test_verifying_the_rank_and_email_unlocks_the_referee_and_is_audited(app_env, monkeypatch):
    calls = fake_selection(monkeypatch)
    case_id, ids = shortlist(app_env)
    at = open_case(app_env, case_id)
    at.text_input(key=f"ref_vemail_{ids[0]}").input("anna.berg@rug.nl")
    at.selectbox(key=f"ref_vrank_{ids[0]}").select("professor")
    at = at.run()
    at.button(key=f"ref_verify_{ids[0]}").click()
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    with app_env.session_scope() as s:
        ref = s.scalar(select(Referee).where(Referee.full_name == "Prof. Anna Berg"))
        assert (ref.email, ref.rank, ref.rank_verified) == ("anna.berg@rug.nl", Rank.PROFESSOR, True)
        entry = s.scalar(select(AuditLogEntry).where(AuditLogEntry.action == "referee_verified"))
        assert entry.case_id == case_id and entry.after["rank_verified"] is True and entry.before["rank_verified"] is False
    assert not at.checkbox(key=f"ref_pick_{ids[0]}").disabled        # now the Chancellor can pick them
    at.checkbox(key=f"ref_pick_{ids[0]}").check()
    at = at.run()
    at.button(key="ref_select").click()
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert calls and calls[0][2] == [ids[0]]


def test_a_bad_email_or_a_missing_rank_is_refused_and_nothing_is_saved(app_env):
    case_id, ids = shortlist(app_env)
    at = open_case(app_env, case_id)
    at.text_input(key=f"ref_vemail_{ids[0]}").input("anna.berg@rug.nl")
    at.button(key=f"ref_verify_{ids[0]}").click()
    at = at.run()
    assert any("Choose the rank" in e.value for e in at.error)
    at.selectbox(key=f"ref_vrank_{ids[0]}").select("professor")
    at.text_input(key=f"ref_vemail_{ids[0]}").input("not-an-email")
    at = at.run()
    at.button(key=f"ref_verify_{ids[0]}").click()
    at = at.run()
    assert any("looks right" in e.value for e in at.error)
    with app_env.session_scope() as s:
        assert s.scalar(select(Referee.rank_verified).where(Referee.full_name == "Prof. Anna Berg")) is False


def test_a_referee_verified_as_associate_professor_stays_locked(app_env):
    case_id, ids = shortlist(app_env, anna_rank=Rank.ASSOCIATE_PROFESSOR, anna_verified=True)
    at = open_case(app_env, case_id)
    assert at.checkbox(key=f"ref_pick_{ids[0]}").disabled
    assert "Verified: Associate Professor" in " ".join(m.value for m in at.markdown)


def test_the_office_can_ask_what_orcid_says(app_env, monkeypatch):
    from promoflow.workflow import outreach
    monkeypatch.setattr(outreach, "suggest_contact", lambda referee_id, get=None: OrcidSuggestion(email=None, role_title="Professor",
                                                                                              looks_full_professor=True))
    case_id, ids = shortlist(app_env)
    at = open_case(app_env, case_id)
    at.button(key=f"ref_ask_{ids[0]}").click()
    at = at.run()
    assert any("current job title **Professor**" in c.value for c in at.caption)


def test_only_the_chancellor_gets_the_page(app_env):
    from promoflow.ui import shell
    with app_env.session_scope() as s:
        token = create_session(s, s.scalar(select(User).where(User.email == "hod.cs@promoflow.test")))
    assert "referees" not in shell.pages_for(_load(token))
    assert "referees" in shell.pages_for(_load(chancellor_token(app_env)))
