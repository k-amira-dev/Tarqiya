"""Every section offers the same two buttons, Automatic upload and Manual upload, and they switch each other on and off."""
import pytest
from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from promoflow.auth.service import create_session
from promoflow.db.models import User
from promoflow.ui.auth import _load
from tests.test_extraction_entry_docs import make_case

# section module -> how many Automatic/Manual pairs its page shows (one per tab or subsection)
PAGES = {"section2": 1, "section3": 1, "section4": 2, "section5": 8, "section6": 9, "section7": 6, "section8": 1, "section9": 1, "section10": 1}


def run(app_env, module: str) -> AppTest:
    make_case(app_env)
    with app_env.session_scope() as s:
        token = create_session(s, s.scalar(select(User).where(User.email == "applicant@promoflow.test")))
    script = f"""
import streamlit as st
from promoflow.ui import theme
from promoflow.ui.views import {module}
theme.inject()
{module}.render()
"""
    at = AppTest.from_string(script, default_timeout=90)
    at.session_state["current_user"] = _load(token)
    return at.run()


def buttons(at: AppTest, label: str):
    return [b for b in at.button if b.label == label]


@pytest.mark.parametrize("module,pairs", PAGES.items())
def test_every_section_has_both_buttons(app_env, module, pairs):
    at = run(app_env, module)
    assert not at.exception, [e.value for e in at.exception]
    assert len(buttons(at, "Automatic upload")) == pairs and len(buttons(at, "Manual upload")) == pairs
    assert not [b for b in at.button if b.label.startswith("+ Add")]                   # the old single "+ Add ..." buttons are gone


def has_box(at: AppTest, key: str) -> bool:
    return any(x.key == key for x in at.text_input)


def reader_open(at: AppTest) -> bool:
    return any(c.value.startswith("Automatic upload ·") for c in at.caption)


def click(at: AppTest, key: str) -> AppTest:
    next(b for b in at.button if b.key == key).click()
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_manual_opens_the_form_and_automatic_opens_the_reader_and_they_exclude_each_other(app_env):
    at = run(app_env, "section3")
    assert not has_box(at, "s3_f_new_uni") and not reader_open(at)                      # neither is open at first
    at = click(at, "ab_s3_editing_manual")                                              # Manual upload: the degree form opens
    assert has_box(at, "s3_f_new_uni") and not reader_open(at)
    at = click(at, "ab_s3_editing_auto")                                                # Automatic upload: the reader opens, the form closes
    assert reader_open(at) and not has_box(at, "s3_f_new_uni")
    at = click(at, "ab_s3_editing_manual")                                              # and back
    assert has_box(at, "s3_f_new_uni") and not reader_open(at)
    at = click(at, "ab_s3_editing_manual")                                              # pressing the open one closes it
    assert not has_box(at, "s3_f_new_uni") and not reader_open(at)


def test_patents_and_creative_works_have_automatic_upload_too(app_env):
    at = run(app_env, "section5")
    for ident in ("s5g_editing", "s5a2_editing"):
        assert next(b for b in at.button if b.key == f"ab_{ident}_auto").disabled is False
        assert next(b for b in at.button if b.key == f"ab_{ident}_manual").disabled is False


def test_a_bar_for_a_type_with_no_reader_disables_only_automatic_upload():
    at = AppTest.from_string("from promoflow.ui.views import entries_ui\nentries_ui.add_bar([], \"\", \"demo_editing\")\n", default_timeout=30).run()
    assert not at.exception
    assert next(b for b in at.button if b.key == "ab_demo_editing_auto").disabled is True
    assert next(b for b in at.button if b.key == "ab_demo_editing_manual").disabled is False


def test_manual_is_blocked_until_a_course_exists_where_a_course_is_needed(app_env):
    at = run(app_env, "section6")
    assert next(b for b in at.button if b.key == "ab_s6b_editing_manual").disabled is True      # peer observations need a course from 6A
    assert next(b for b in at.button if b.key == "ab_s6a_editing_manual").disabled is False      # 6A is where courses are added


# the document type each page's Automatic panels read (the caption of an open panel names it)
NOUNS = {"section2": ["your CV"], "section3": ["academic degrees", "equivalency certificates"], "section4": ["academic rank decisions", "non-academic positions"],
         "section5": ["published papers", "acceptance letters", "book chapters", "conference papers", "funded research projects", "awards", "the Scopus profile screenshot", "patents", "creative works"],
         "section6": ["peer observation reports", "curriculum contributions", "teaching innovation reports", "syllabi (course files)", "workshops and seminars you attended",
                      "thesis supervision records"],
         "section7": ["committee appointments", "administrative appointments", "workshops you organised or gave", "trainings you delivered", "policy contributions",
                      "community activities"],
         "section8": ["recommendation letters"], "section9": ["the signed conditions form"], "section10": ["the signed cover letter"]}


@pytest.mark.parametrize("module,nouns", NOUNS.items())
def test_every_automatic_panel_of_a_page_opens_and_names_its_documents(app_env, module, nouns):
    at = run(app_env, module)
    for key in [b.key[:-5] for b in at.button if b.key.endswith("_auto") and not b.disabled]:
        at.session_state[key] = "auto"                                                  # switch every Automatic panel of the page on at once
    at = at.run()
    assert not at.exception, (module, [e.value for e in at.exception])
    captions = " | ".join(c.value for c in at.caption if c.value.startswith("Automatic upload ·"))
    for noun in nouns:
        assert noun in captions, (module, noun, captions)
