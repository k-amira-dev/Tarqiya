"""More evidence documents -> entries (degrees, ranks, papers, awards, peer observations ...): the rules in extraction/entry_docs_more.py and
saving through the sections' own add() functions. Fake models stand in for Groq, so nothing here costs money or needs a key."""
from datetime import date
from types import SimpleNamespace

from sqlalchemy import select

from promoflow.db.models import (
    Award, CourseTaught, CurriculumContribution, Degree, PeerObservation, Publication, RankHistory,
)
from promoflow.extraction import entry_docs as E
from promoflow.extraction import entry_docs_more as M
from promoflow.dossier import doc_entries
from tests.test_extraction_entry_docs import FIXTURES, draft, make_case
from tests.test_extraction_teaching_docs import FakeLLM

COURSES = [SimpleNamespace(id=1, course_code="MCOM 325", academic_year="2018/2019", semester="fall", role="instructor"),
           SimpleNamespace(id=2, course_code="MCOM 325", academic_year="2019/2020", semester="fall", role="instructor"),
           SimpleNamespace(id=3, course_code="MCOM 230", academic_year="2023/2024", semester="fall", role="instructor")]
CTX = E.Ctx(applicant_name="Dr. Samira Al-Tamimi", courses=COURSES,
            journals={M.norm_name("Frontiers in Sociology"): ("2673-5172", "Frontiers Media SA")})


# ---- degrees, ranks, positions ---------------------------------------------------------------------------------------

def test_a_phd_certificate_becomes_a_degree_but_the_study_start_is_left_to_the_applicant():
    v, issues = M.build_degree(M.DegreeCert(degree_name="Doctor of Philosophy", field_of_study="Media and Communication", university="University of Westbridge",
                                            country="United Kingdom", conferral_date="12 July 2016", thesis_title="Participatory practices"), CTX)
    assert (v["level"], v["country_code"], v["graduation_date"], v["study_to"]) == ("phd", "GB", date(2016, 7, 12), date(2016, 7, 12))
    assert issues == ["study period start is not on the certificate: enter it"]


def test_a_master_degree_without_a_thesis_title_is_flagged():
    _, issues = M.build_degree(M.DegreeCert(degree_name="Master of Arts", field_of_study="Journalism", university="X University", country="Jordan",
                                            conferral_date="2010-06-30", thesis_title=None), CTX)
    assert "thesis title not found" in issues


def test_an_unknown_degree_or_country_is_not_guessed():
    v, issues = M.build_degree(M.DegreeCert(degree_name="Certificate", field_of_study="X", university="U", country="Atlantis", conferral_date="2010-06-30", thesis_title=None), CTX)
    assert v["level"] is None and v["country_code"] is None and "degree level not understood" in issues and "choose the country" in issues


def test_a_rank_decision_here_is_at_this_university_in_the_uae():
    v, issues = M.build_rank(M.RankDecision(rank_title="Assistant Professor", institution="University of Sharjah", country=None, effective_date="01 September 2018",
                                            decision_date="14 August 2018"), CTX)
    assert issues == [] and (v["rank"], v["held_from"], v["country_code"], v["at_this_university"]) == ("assistant_professor", date(2018, 9, 1), "AE", True)


def test_professor_is_not_taken_for_associate_or_assistant():
    for title, code in (("Associate Professor", "associate_professor"), ("Professor", "professor"), ("Lecturer", "lecturer")):
        assert M.build_rank(M.RankDecision(rank_title=title, institution="Gulf Coast University", country="Kuwait", effective_date="2016-09-01", decision_date=None), CTX)[0]["rank"] == code


def test_a_contract_becomes_a_non_academic_position():
    v, issues = M.build_position(M.EmploymentDoc(position="Digital News Editor", employer="Horizon Media Group", country="Jordan", date_from="01 July 2011",
                                                 date_to="31 August 2012"), CTX)
    assert issues == [] and (v["country_code"], v["date_to"]) == ("JO", date(2012, 8, 31))


# ---- papers ----------------------------------------------------------------------------------------------------------

def paper(**kw):
    base = dict(title="Algorithmic Visibility", journal_name="Frontiers in Sociology", publisher="Frontiers Media SA", issn=None, volume="8", issue="1", pages="1184502",
                doi="10.9999/pf.d01.001 (invented)", year=2023, month="June", authors=["S. Al-Tamimi", "R. Haddad", "M. Okafor"], corresponding_author=None,
                affiliation="Department of Mass Communication, University of Sharjah, United Arab Emirates")
    return M.PaperDoc(**{**base, **kw})


def test_a_paper_gives_the_position_role_issn_and_clean_doi():
    v, issues = M.build_paper(paper(), CTX)
    assert issues == []
    assert (v["author_position"], v["total_authors"], v["applicant_role"], v["main_author_basis"]) == (1, 3, "main", "first_author")
    assert (v["issn"], v["doi"], v["_other_authors"], v["at_this_university"]) == ("2673-5172", "10.9999/pf.d01.001", ["R. Haddad", "M. Okafor"], True)


def test_a_sole_author_and_a_second_author():
    assert M.build_paper(paper(authors=["S. Al-Tamimi"]), CTX)[0]["applicant_role"] == "sole"
    v, _ = M.build_paper(paper(authors=["L. Farouk", "S. Al-Tamimi"]), CTX)
    assert (v["author_position"], v["applicant_role"]) == (2, "co_author")
    v, _ = M.build_paper(paper(authors=["L. Farouk", "S. Al-Tamimi"], corresponding_author="S. Al-Tamimi"), CTX)
    assert (v["applicant_role"], v["main_author_basis"]) == ("main", "corresponding_author")


def test_a_paper_without_issn_issue_or_month_asks_for_them():
    v, issues = M.build_paper(paper(journal_name="Unknown Journal", issue=None, month=None), CTX)
    assert "ISSN not found: enter it" in issues and "issue number not printed: enter it" in issues
    assert any(i.startswith("check:") for i in issues) and v["issue_date"] == date(2023, 1, 1)


def test_a_check_note_does_not_block_a_draft():
    d = E.EntryDraft("paper", "p.pdf", b"", {}, ["check: only the year is printed"], "text")
    assert d.ok and not E.EntryDraft("paper", "p.pdf", b"", {}, ["ISSN not found: enter it"], "text").ok


def test_a_name_missing_from_the_author_list_is_flagged_and_arabic_is_detected():
    v, issues = M.build_paper(paper(title="استخدام الصحفيين", authors=["A. Someone"]), CTX)
    assert v["language"] == "arabic" and "your position was not found in the author list (names in Arabic are not matched): enter your position and role" in issues


def test_an_acceptance_letter_makes_an_accepted_paper():
    v, issues = M.build_acceptance(M.AcceptanceLetter(title="Audience Engagement Metrics", journal_name="Frontiers in Sociology", publisher=None,
                                                      authors=["R. Haddad", "S. Al-Tamimi"], acceptance_date="12 September 2026"), CTX)
    assert (v["status"], v["acceptance_date"], v["applicant_role"], v["publisher"]) == ("accepted", date(2026, 9, 12), "co_author", "Frontiers Media SA")
    assert [i for i in issues if not i.startswith("check:")] == []


# ---- the other research items ----------------------------------------------------------------------------------------

def test_a_book_chapter_where_the_applicant_is_the_only_author():
    v, issues = M.build_book(M.BookChapterDoc(book_title="Media and Society", chapter_title="Participation", publisher="Northgate", publication_year=2024,
                                              isbn="978-0-0000-0000-0 (simulated)", authors=["Samira Al-Tamimi"]), CTX)
    assert issues == [] and (v["item_type"], v["main_or_sole_author"], v["isbn"], v["publication_date"]) == ("chapter", True, "978-0-0000-0000-0", date(2024, 1, 1))


def test_a_conference_paper_leaves_scopus_to_the_applicant():
    v, issues = M.build_conference(M.ConferencePaperDoc(title="Fact-Checking", conference_title="ICDMS 2022", organizer="Gulf Media Research Association", place="Dubai, UAE",
                                                        conference_date="14 November 2022", pages="112-119", doi=None, authors=["Samira Al-Tamimi"]), CTX)
    assert v["main_or_sole_author"] is True and v["scopus_indexed"] is None and issues == ["say whether the proceedings are indexed in Scopus"]


def test_a_funded_project_with_the_applicant_as_principal_investigator():
    v, issues = M.build_funded(M.FundedProjectDoc(title="Misinformation", funding_body="University of Sharjah Competitive Research Grant", amount=85000, currency="aed",
                                                  start_date="01 January 2023", end_date="31 December 2024", applicant_role="Principal Investigator", status="Completed"), CTX)
    assert issues == [] and (v["funder_code"], v["role"], v["status"], v["currency"]) == ("internal", "pi", "completed", "AED")
    assert M.build_funded(M.FundedProjectDoc(title="t", funding_body="Ministry of Education", amount=1, currency="AED", start_date="2020-01-01", end_date=None,
                                             applicant_role="Co-investigator", status="Ongoing"), CTX)[0]["role"] == "ci"


def test_an_award_scope_comes_from_who_gives_it():
    def scope(body, context=None):
        return M.build_award(M.AwardDoc(award_name="Award", awarding_body=body, award_date="5th of June 2022", context=context), CTX)[0]["scope_code"]
    assert scope("College of Communication, University of Sharjah") == "institutional"
    assert scope("Gulf Media Research Association") == "regional"
    assert scope("International Association of Media", None) == "international"
    assert scope("Some Club") is None
    assert M.build_award(M.AwardDoc(award_name="A", awarding_body="B", award_date="5th of June 2022", context=None), CTX)[0]["year"] == 2022


def test_scopus_numbers_and_a_missing_date():
    v, issues = M.build_scopus(M.ScopusDoc(h_index=7, total_citations=312, screenshot_date=None), CTX)
    assert (v["h_index"], v["total_citations"]) == (7, 312) and issues == ["no date on the screenshot: enter the date it was taken"]


# ---- teaching and service --------------------------------------------------------------------------------------------

def test_a_peer_observation_is_matched_to_the_right_course_semester():
    v, issues = M.build_peer_observation(M.PeerObservationDoc(course_code="MCOM325", term="Fall 2019", observer_name="Prof. Karim Al-Masri", observer_role="Peer faculty member",
                                                              observation_date="15 October 2019", overall_score=4.0, scale_max=5), CTX)
    assert issues == [] and (v["course_taught_id"], v["observer_code"], v["rating"], v["scale_max"]) == (2, "peer", 4.0, 5.0)


def test_an_unclear_course_is_left_to_the_applicant():
    _, issues = M.build_peer_observation(M.PeerObservationDoc(course_code="MCOM 325", term=None, observer_name=None, observer_role="Head of Department",
                                                              observation_date="2019-10-15", overall_score=4, scale_max=5), CTX)
    assert issues == ["course not matched to your courses: choose it"]
    assert M.match_course_row("MCOM 999", "Fall 2018", CTX) is None


def test_the_curriculum_summary_gives_one_entry_per_row():
    new = M.build_curriculum_row(M.CurriculumRow(course_code="MCOM 415", course_title="Data Journalism", contribution="Proposed a new course", changes="New course",
                                                 approval_level="University level", approval_date="12 May 2021", what_was_done="Designed the course."), CTX)
    mod = M.build_curriculum_row(M.CurriculumRow(course_code="MCOM 310", course_title="Digital Journalism", contribution="Modified an existing course",
                                                 changes="Objectives changed, Textbook replaced", approval_level="College level", approval_date="18 May 2022",
                                                 what_was_done="Rewrote the objectives."), CTX)
    assert new[1] == [] and (new[0]["type_code"], new[0]["changes"], new[0]["self_classification"], new[0]["approved_by"]) == ("new_course", None, None, "university")
    assert mod[1] == [] and (mod[0]["changes"], mod[0]["self_classification"]) == (["textbook", "objectives"], "deep")


def test_a_teaching_innovation_report():
    v, issues = M.build_innovation(M.InnovationDoc(title="AI-assisted draft feedback in Media Writing", course_code="MCOM 230", term="Fall 2023",
                                                   what_was_done="Weekly drafts with AI feedback.", measured_outcome="Turnaround 7 to 2 days."), CTX)
    assert issues == [] and (v["type_code"], v["course_taught_id"]) == ("ai_tool", 3)


def test_a_policy_document_takes_the_applicants_role_and_the_level_from_the_approving_body():
    v, issues = M.build_policy(M.PolicyDoc(policy_name="Policy on Generative AI", approving_body="Department Council of Mass Communication", effective_date="05 Jun 2024",
                                           applicant_role="Chair"), CTX)
    assert issues == [] and (v["level"], v["role_code"], v["activity_date"]) == ("department", "chaired", date(2024, 6, 5))


def test_a_syllabus_is_matched_to_a_course_and_the_platform_is_left_open():
    v, issues = M.build_course_file(M.SyllabusDoc(course_code="MCOM 230", term="Fall 2023"), CTX)
    assert (v["course_taught_id"], v["items"], v["is_coordinator"]) == (3, ["syllabus"], False) and issues == ["choose where the course file is kept"]


def test_a_recommendation_letter_relationship():
    v, _ = M.build_letter(M.LetterDoc(writer_name="Prof. X", writer_rank="Professor", writer_institution="Y University", relationship="my former PhD supervisor"), CTX)
    assert v["relationship_code"] == "former_supervisor"


def test_every_kind_has_a_saving_function():
    assert set(E.KINDS) - set(doc_entries.ADDERS) == {"equivalency"}


# ---- reading with fake models ----------------------------------------------------------------------------------------

def test_several_curriculum_rows_come_from_one_document():
    rows = [M.CurriculumRow(course_code="MCOM 415", course_title="Data Journalism", contribution="Proposed a new course", changes="New course",
                            approval_level="University level", approval_date="2021-05-12", what_was_done="Designed it."),
            M.CurriculumRow(course_code="MCOM 230", course_title="Media Writing", contribution="Modified an existing course", changes="Content updated",
                            approval_level="Department level", approval_date="2024-05-09", what_was_done="Updated it.")]
    text_pdf = (FIXTURES / "student_evaluation_b.pdf").read_bytes()
    drafts, _ = E.read_entries(E.KINDS["curriculum"], "c.pdf", text_pdf, CTX, FakeLLM(M.CurriculumDoc(rows=rows)), None)
    assert [d.values["course_or_program"] for d in drafts] == ["MCOM 415 Data Journalism", "MCOM 230 Media Writing"]


# ---- saving ----------------------------------------------------------------------------------------------------------

def ctx_for(app_env, uid):
    with app_env.session_scope() as s:
        return doc_entries.load_ctx(s, "Dr. Samira Al-Tamimi", uid)


def test_degree_then_equivalency_attaches_the_second_file(app_env):
    uid = make_case(app_env)
    ctx = ctx_for(app_env, uid)
    v = dict(level="phd", specialization="Media", university="University of Westbridge", country_code="GB", study_from=date(2012, 9, 1), study_to=date(2016, 7, 12),
             graduation_date=date(2016, 7, 12), thesis_title="Thesis", equivalency_required=False)
    with app_env.session_scope() as s:
        assert doc_entries.add_entries(s, uid, "degree", [draft("degree", v, "phd.pdf")], ctx).added == 1
    eq = dict(qualification="PhD", institution="University of Westbridge, United Kingdom", award_date=date(2016, 7, 12))
    with app_env.session_scope() as s:
        first = doc_entries.add_entries(s, uid, "equivalency", [draft("equivalency", eq, "eq.pdf")], ctx)
    with app_env.session_scope() as s:
        second = doc_entries.add_entries(s, uid, "equivalency", [draft("equivalency", eq, "eq.pdf")], ctx)
        degree = s.scalars(select(Degree)).one()
    assert (first.added, second.skipped_existing, degree.equivalency_required) == (1, 1, True)


def test_an_equivalency_without_a_matching_degree_is_reported(app_env):
    uid = make_case(app_env)
    ctx = ctx_for(app_env, uid)
    with app_env.session_scope() as s:
        out = doc_entries.add_entries(s, uid, "equivalency", [draft("equivalency", dict(qualification="PhD", institution="Nowhere", award_date=date(2000, 1, 1)), "eq.pdf")], ctx)
    assert out.added == 0 and "no degree" in out.rejected[0]


def test_ranks_get_their_end_dates_from_the_next_rank(app_env):
    uid = make_case(app_env)
    ctx = ctx_for(app_env, uid)
    lecturer = dict(rank="lecturer", date_obtained=date(2016, 9, 1), university="Gulf Coast University", country_code="KW", held_from=date(2016, 9, 1), held_to=None, at_this_university=False)
    assistant = dict(rank="assistant_professor", date_obtained=date(2018, 9, 1), university="University of Sharjah", country_code="AE", held_from=date(2018, 9, 1), held_to=None,
                     at_this_university=True)
    with app_env.session_scope() as s:
        out = doc_entries.add_entries(s, uid, "rank", [draft("rank", assistant, "b.pdf"), draft("rank", lecturer, "a.pdf")], ctx)
        rows = {r.rank.value: r for r in s.scalars(select(RankHistory))}
    assert out.added == 2 and rows["lecturer"].held_to == date(2018, 9, 1) and rows["assistant_professor"].held_to is None


def test_a_published_paper_is_saved_with_its_authors(app_env):
    uid = make_case(app_env)
    ctx = ctx_for(app_env, uid)
    values, issues = M.build_paper(paper(issn="2673-5172"), ctx)
    assert issues == [] or all(i.startswith("check:") for i in issues)
    d = E.EntryDraft("paper", "p.pdf", b"%PDF-1.4 test", dict(values), issues, "text")
    doc_entries.precheck("paper", [d], ctx)
    assert d.ok
    with app_env.session_scope() as s:
        out = doc_entries.add_entries(s, uid, "paper", [d], ctx)
        p = s.scalars(select(Publication)).one()
        got = (p.author_position, p.total_authors, p.status.value, p.applicant_role.value, len(p.authors))
    assert out.added == 1 and got == (1, 3, "published", "main", 3)


def test_precheck_shows_the_sections_own_errors_before_saving(app_env):
    uid = make_case(app_env)
    ctx = ctx_for(app_env, uid)
    values, _ = M.build_book(M.BookChapterDoc(book_title="B", chapter_title="C", publisher="P", publication_year=2024, isbn="978-0-0000-0000-0", authors=["Samira Al-Tamimi"]), ctx)
    d = E.EntryDraft("book", "b.pdf", b"%PDF", values, [], "text")
    doc_entries.precheck("book", [d], ctx)
    assert any("ISBN" in i for i in d.issues) and not d.ok


def test_a_peer_observation_and_a_curriculum_entry_are_saved(app_env):
    uid = make_case(app_env)
    with app_env.session_scope() as s:
        case = doc_entries.active_case(s, uid)
        s.add(CourseTaught(case_id=case.id, academic_year="2018/2019", semester="fall", course_code="MCOM 325", course_title="Audience Research Methods", level="undergraduate",
                           sections=1, students=30, role="instructor", delivery_mode="face_to_face"))
    ctx = ctx_for(app_env, uid)
    assert [c.course_code for c in ctx.courses] == ["MCOM 325"]
    obs, issues = M.build_peer_observation(M.PeerObservationDoc(course_code="MCOM 325", term="Fall 2018", observer_name="Prof. K", observer_role="Peer faculty member",
                                                                observation_date="15 October 2018", overall_score=4.0, scale_max=5), ctx)
    assert issues == []
    cur, _ = M.build_curriculum_row(M.CurriculumRow(course_code="MCOM 415", course_title="Data Journalism", contribution="Proposed a new course", changes=None,
                                                    approval_level="University level", approval_date="12 May 2021", what_was_done="Designed the course."), ctx)
    with app_env.session_scope() as s:
        a = doc_entries.add_entries(s, uid, "peer_observation", [draft("peer_observation", obs, "o.pdf")], ctx)
        b = doc_entries.add_entries(s, uid, "curriculum", [draft("curriculum", cur, "c.pdf")], ctx)
        o, c = s.scalars(select(PeerObservation)).one(), s.scalars(select(CurriculumContribution)).one()
    assert (a.added, b.added, float(o.rating), c.course_or_program) == (1, 1, 4.0, "MCOM 415 Data Journalism")


def test_an_award_is_saved_with_its_scope(app_env):
    uid = make_case(app_env)
    ctx = ctx_for(app_env, uid)
    values, issues = M.build_award(M.AwardDoc(award_name="Excellence in Teaching Award", awarding_body="College of Communication, University of Sharjah", award_date="5 June 2022",
                                              context=None), ctx)
    assert issues == []
    with app_env.session_scope() as s:
        out = doc_entries.add_entries(s, uid, "award", [draft("award", values, "a.pdf")], ctx)
        row = s.scalars(select(Award)).one()
    assert out.added == 1 and row.year == 2022


# ---- the pages show the panels ---------------------------------------------------------------------------------------

def _labels(node) -> list[str]:
    """The labels of every element on the page (AppTest lists an expander with an icon under a different type, so walk the tree)."""
    out = [getattr(node, "label", "") or ""]
    for child in getattr(node, "children", {}).values():
        out += _labels(child)
    return out


def test_every_section_page_shows_its_document_panels(app_env):
    """Each page renders (headless) for an applicant with a draft application, and offers the 'Fill in from your documents' panels it should."""
    from streamlit.testing.v1 import AppTest
    from promoflow.auth.service import create_session
    from promoflow.db.models import User
    from promoflow.ui.auth import _load

    make_case(app_env)
    with app_env.session_scope() as s:
        token = create_session(s, s.scalar(select(User).where(User.email == "applicant@promoflow.test")))
    expected = {
        "section2": ["your CV"], "section3": ["academic degrees", "equivalency certificates"], "section4": ["academic rank decisions", "non-academic positions"],
        "section5": ["published papers", "acceptance letters", "book chapters", "conference papers", "funded research projects", "awards", "Scopus"],
        "section6": ["peer observation", "curriculum contributions", "teaching innovation", "syllabi"], "section7": ["policy contributions"],
        "section8": ["recommendation letters"], "section9": ["signed conditions form"], "section10": ["signed cover letter"],
    }
    for module, nouns in expected.items():
        script = f"from promoflow.ui import theme\nfrom promoflow.ui.views import {module}\ntheme.inject()\n{module}.render()\n"
        at = AppTest.from_string(script, default_timeout=60)
        at.session_state["current_user"] = _load(token)
        at = at.run()
        assert not at.exception, (module, [e.value for e in at.exception])
        labels = " | ".join(_labels(at.main))
        for noun in nouns:
            assert noun in labels, (module, noun, labels)


def test_the_study_start_is_filled_from_the_cv_with_a_check_note():
    v, issues = M.build_degree(M.DegreeCert(degree_name="Bachelor of Arts", field_of_study="Mass Communication", university="Al-Noor University", country="Jordan",
                                            conferral_date="15 July 2008", thesis_title=None), CTX)
    d = E.EntryDraft("degree", "b.pdf", b"", v, issues, "picture")
    M.fill_study_years([d], [M.CvDegreeRow(degree="BA", institution="Al-Noor University", years="2004-2008"),
                             M.CvDegreeRow(degree="MA", institution="Eastbridge University", years="2009-2011")])
    assert d.values["study_from"] == date(2004, 9, 1) and d.ok and d.issues[0].startswith("check:")


def test_choosing_a_certificate_in_the_degree_form_fills_its_boxes(app_env):
    """The form's own boxes (not only the panel) are filled when a file is chosen in its file box."""
    from streamlit.testing.v1 import AppTest
    from promoflow.auth.service import create_session
    from promoflow.db.models import User
    from promoflow.ui.auth import _load

    make_case(app_env)
    with app_env.session_scope() as s:
        token = create_session(s, s.scalar(select(User).where(User.email == "applicant@promoflow.test")))
    script = '''
from datetime import date
from types import SimpleNamespace
import streamlit as st
from promoflow.extraction import entry_docs as E
from promoflow.extraction import entry_docs_more as M
from promoflow.ui import theme
from promoflow.ui.views import entries_ui, section3

def fake_read(kind, name, data, ctx, text_llm, vision_llm):
    values, issues = M.build_degree(M.DegreeCert(degree_name="Bachelor of Arts", field_of_study="Mass Communication", university="Al-Noor University",
                                                 country="Jordan", conferral_date="15 July 2008", thesis_title=None), ctx)
    return [E.EntryDraft("degree", name, data, values, issues, "picture")], None

entries_ui.read_entries = fake_read
entries_ui._models = lambda: ("text", "vision")
theme.inject()
st.session_state["s3_editing"] = "new"
entries_ui._chosen_file = lambda key: SimpleNamespace(name="bsc.pdf", getvalue=lambda: b"%PDF-1.4 x") if key == "s3_f_new_cert" else None
section3.render()
'''
    at = AppTest.from_string(script, default_timeout=60)
    at.session_state["current_user"] = _load(token)
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.text_input(key="s3_f_new_uni").value == "Al-Noor University"
    assert at.text_input(key="s3_f_new_spec").value == "Mass Communication"
    assert at.selectbox(key="s3_f_new_country").value == "JO"
    assert at.date_input(key="s3_f_new_grad").value == date(2008, 7, 15)


def test_uploading_the_classification_form_makes_the_papers_journals_count(app_env):
    from promoflow.db.enums import JournalClass
    from promoflow.dossier.section5 import classification as cf
    from promoflow.dossier.section5 import papers as s5p

    uid = make_case(app_env)
    ctx = ctx_for(app_env, uid)
    drafts = []
    for issn, journal, authors in (("2297-7775", "Frontiers in Sociology", ["S. Al-Tamimi", "R. Haddad"]), ("2325-8071", "Studies in Media and Communication", ["S. Al-Tamimi"])):
        values, _ = M.build_paper(paper(title=f"Paper in {journal}", journal_name=journal, issn=issn, authors=authors, issue="1"), ctx)
        drafts.append(E.EntryDraft("paper", "p.pdf", b"%PDF-1.4 test", values, [], "text"))
    with app_env.session_scope() as s:
        assert doc_entries.add_entries(s, uid, "paper", drafts, ctx).added == 2
    form = cf.ClassificationForm(journals=[cf.FormJournal(journal_name="Frontiers in Sociology", journal_name_arabic=None, classification="Q1"),
                                           cf.FormJournal(journal_name="Studies in Media and Communication", journal_name_arabic=None, classification="Q3-B")])
    with app_env.session_scope() as s:
        case = doc_entries.active_case(s, uid)
        before = {r.publication.title: r.classification.journal_class for r in s5p.load(s, case.id)}
        added = cf.declare_journals_from_form(s, case.id, form, 2026)
        again = cf.declare_journals_from_form(s, case.id, form, 2026)
        for p in s.scalars(select(Publication)):
            if "Frontiers" in p.title:
                p.impact_factor = 2.5            # Class A also needs the paper's ISI impact factor
        s.flush()
        after = {r.publication.title: r.classification.journal_class for r in s5p.load(s, case.id)}
    assert set(before.values()) == {JournalClass.NOT_COUNTED} and len(added) == 2 and again == []
    assert after == {"Paper in Frontiers in Sociology": JournalClass.CLASS_A, "Paper in Studies in Media and Communication": JournalClass.CLASS_B}


def test_arabic_journal_names_match_across_look_alike_letters():
    from promoflow.dossier.section5 import classification as cf
    assert cf._norm("مجلة حولیات الآداب والعلوم الاجتماعیة") == cf._norm("مجلة حوليات الآداب والعلوم الاجتماعية")
