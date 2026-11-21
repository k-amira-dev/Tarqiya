"""The applicant assistant: the facts it reads, and the answers built from them. A fake model stands in for the language model, so no test
calls a provider. `app_env` (see conftest.py) is a fresh temporary database seeded with the reference data and test accounts."""
import json
from datetime import date

from sqlalchemy import select

from promoflow.assistant import chat, tools
from promoflow.db.enums import PromotionTrack, Rank
from promoflow.db.models import User
from promoflow.dossier import section0 as s0

TODAY = date(2026, 9, 25)
S0_VALUES = {
    "academic_year": "2026/2027", "track": PromotionTrack.TO_ASSOCIATE, "specialization": "Computer Science",
    "fine_specialization": "Machine Learning", "research_keywords": [], "appointment_date": date(2019, 9, 1),
    "rank_on_appointment": Rank.ASSISTANT_PROFESSOR, "current_rank_date": date(2019, 9, 1), "scopus_author_id": "57193456789", "orcid": None,
    "phd_outside_uae": False, "early_application": False, "exceptional_case": False, "exceptional_justification": None,
    "previously_rejected": False, "rejection_date": None,
}


def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


class FakeModel:
    """Records what it was sent and answers with a fixed text (or raises)."""
    def __init__(self, text="Open Section 3 to add your degrees.", error=None):
        self.text, self.error, self.sent = text, error, None

    def invoke(self, messages):
        self.sent = messages
        if self.error:
            raise self.error
        return type("R", (), {"content": self.text})()


def test_section_paths_match_the_navigation():
    from promoflow.ui import shell
    assert tools.SECTION_PATHS == {code: url for code, _t, _i, url, _r in shell.SECTIONS}


def test_no_case_means_start_with_section_zero(app_env):
    with app_env.session_scope() as s:
        status = tools.dossier_status(s, applicant(s).id, TODAY)
    assert status["has_case"] is False and status["gaps"][0]["section"] == "0"
    assert "Section 0" in chat.render_missing({"status": status, "requirements": {}, "today": ""}).text


def test_status_lists_what_is_missing_with_the_page_to_open(app_env):
    with app_env.session_scope() as s:
        s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)
    with app_env.session_scope() as s:
        status = tools.dossier_status(s, applicant(s).id, TODAY)
    assert status["has_case"] and status["editable"] and not status["can_submit"]
    by = {g["section"]: g for g in status["gaps"] if g["kind"] == "section"}
    assert "3" in by and by["3"]["page"] == "degrees" and "0" not in by       # degrees missing, Section 0 is filled
    assert any(g["kind"] == "research" for g in status["gaps"])                # no papers: the research minimums are not met
    assert status["research"][0]["need"] >= 1


def test_requirements_come_from_the_database_for_the_track(app_env):
    with app_env.session_scope() as s:
        rq = tools.requirements(s, PromotionTrack.TO_ASSOCIATE, TODAY)
    labels = {t["label"]: t["value"] for t in rq["thresholds"]}
    assert labels["Minimum total publications"] > 0 and "Minimum years in the current rank" in labels
    assert [f["total_points"] for f in rq["scoring_forms"]] == [30.0, 10.0]
    assert all(not it["full_professor_only"] for f in rq["scoring_forms"] for it in f["items"])      # an Associate track never sees Full-only items


def test_facts_hold_no_personal_data(app_env):
    with app_env.session_scope() as s:
        s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)
        user = applicant(s)
        blob = json.dumps(tools.facts(s, user.id, TODAY), default=str)
        assert user.email not in blob and (user.full_name or "\x00") not in blob and "57193456789" not in blob


def _facts(app_env):
    with app_env.session_scope() as s:
        s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)
    with app_env.session_scope() as s:
        return tools.facts(s, applicant(s).id, TODAY)


def test_question_kinds():
    assert chat.intent("What's missing from my application?") == "missing"
    assert chat.intent("What do I still need to do?") == "missing"
    assert chat.intent("What do I need for my track?") == "requirements"
    assert chat.intent("Am I eligible yet?") == "eligibility"
    assert chat.intent("Please submit my application for me") == "action"
    assert chat.intent("What is a Class A journal?") is None


def test_missing_answer_needs_no_model_and_names_the_sections(app_env):
    facts = _facts(app_env)
    model = FakeModel()
    got = chat.reply("What is missing?", facts, llm=model)
    assert model.sent is None and not got.model                                # answered from the facts, no model call
    assert "Section 3" in got.text and "3" in got.sections and "cannot submit" in got.text


def test_requirements_answer_lists_the_thresholds(app_env):
    got = chat.reply("What do I need for my track?", _facts(app_env), llm=FakeModel())
    assert "Minimum total publications" in got.text and "pass mark 24" in got.text


def test_a_request_to_submit_is_declined(app_env):
    got = chat.reply("submit my application now", _facts(app_env), llm=FakeModel())
    assert "cannot submit" in got.text and "11" not in got.sections and not got.model


def test_free_questions_go_to_the_model_with_the_facts_and_without_personal_data(app_env):
    facts = _facts(app_env)
    model = FakeModel("Open Section 3 to add your degrees, then Section 5.")
    got = chat.reply("Who is the best person to ask? my email is dr.someone@uos.ac.ae", facts, llm=model, user_name="Dr. Test Person")
    assert got.model and got.sections == ["3", "5"]
    sent = " ".join(str(m.content) for m in model.sent)
    assert "dr.someone@uos.ac.ae" not in sent and "FACTS" in sent and "Minimum total publications" in sent


def test_a_wrong_claim_of_readiness_is_replaced_by_the_checklist(app_env):
    facts = _facts(app_env)
    got = chat.reply("Tell me about my progress", facts, llm=FakeModel("Great news, you are ready to submit!"))
    assert not got.model and "still missing" in got.text


def test_when_the_model_fails_the_checklist_is_still_shown(app_env):
    got = chat.reply("Explain the process", _facts(app_env), llm=FakeModel(error=RuntimeError("rate limited")))
    assert not got.model and "checklist" in got.text and "Section 3" in got.text


def test_empty_question():
    assert "what is missing" in chat.reply("  ", {"status": {}, "requirements": {}}).text.lower()


def test_the_model_gets_the_policy_definitions_the_application_uses(app_env):
    facts = _facts(app_env)
    model = FakeModel("Class A means top 20% in Scopus and ISI-listed. See Section 5.")
    chat.reply("What is a Class A journal?", facts, llm=model)
    sent = " ".join(str(m.content) for m in model.sent)
    assert "top 20%" in sent and "ISI" in sent and "do not use general knowledge" in sent
