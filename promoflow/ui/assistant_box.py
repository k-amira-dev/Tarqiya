"""The assistant chat box: a round button fixed in the bottom-right corner of every page that opens a small chat panel.

Applicants only. It reads the applicant's own checklist (promoflow.assistant) and never writes anything. The conversation lives in the browser
session (`st.session_state`), so it survives moving between pages and is gone when the session ends.
"""
from datetime import date

import time

import streamlit as st

from promoflow.assistant import chat, tools
from promoflow.db import session as db_session
from promoflow.db.enums import RoleName
from promoflow.ui import shell

KEY = "pf_assistant"
HISTORY = "pf_assistant_history"
SIZE = "pf_assistant_panel_size"
SIZES = {"compact": (430, 330, 40), "large": (780, 440, 46)}       # panel width (px), conversation height (px) and its cap as a share of the window height (vh)
FACTS = "pf_assistant_facts"
FACTS_SECONDS = 15
MAX_QUESTIONS = 40                    # per browser session: protects the model allowance shared with the review agents

CSS = """
<style>
.st-key-pf_assistant{position:fixed;right:22px;bottom:22px;z-index:1000;width:auto!important}
.st-key-pf_assistant button[kind="secondary"]{border-radius:999px!important;background:#0B0D0C!important;color:#fff!important;
  border:2px solid #00B386!important;padding:.55rem 1.05rem!important;box-shadow:0 6px 18px rgba(0,0,0,.28)}
.st-key-pf_assistant button[kind="secondary"] p{color:#fff!important;font-weight:600}
div[data-testid="stPopoverBody"]{min-width:320px;left:auto!important;top:auto!important;right:22px!important;bottom:84px!important;
  transform:none!important;max-height:calc(100vh - 110px)!important}
div[data-testid="stPopoverBody"] div[data-testid="InputInstructions"]{display:none!important}
</style>
"""


def _ask(user, question: str) -> None:
    """Answer one question and add both lines to the conversation."""
    history = st.session_state.setdefault(HISTORY, [])
    asked = sum(1 for m in history if m["role"] == "user")
    history.append({"role": "user", "content": question})
    if asked >= MAX_QUESTIONS:
        history.append({"role": "assistant", "content": "You have reached the question limit for this session. Reload the page to start again.", "sections": []})
        return
    cached = st.session_state.get(FACTS)
    if cached and cached[0] == user.id and time.time() - cached[1] < FACTS_SECONDS:        # the database is remote: do not ask again for every question
        facts = cached[2]
    else:
        with db_session.session_scope() as s:
            facts = tools.facts(s, user.id, date.today())
        st.session_state[FACTS] = (user.id, time.time(), facts)
    with st.spinner("Checking your application..."):
        got = chat.reply(question, facts, [{"role": m["role"], "content": m["content"]} for m in history[:-1]], user_name=user.full_name)
    history.append({"role": "assistant", "content": got.text, "sections": got.sections})


def _links(sections: list[str]) -> None:
    pages = st.session_state.get("pf_pages", {})
    titles = {code: title for code, title, *_ in shell.SECTIONS}
    for code in sections:
        page = pages.get(f"section{code}")
        if page is not None:
            st.page_link(page, label=f"Open {code} · {titles.get(code, '')}", icon=":material/arrow_forward:")


def render(user) -> None:
    """Draw the button and, when opened, the chat panel. Call once per run, after the navigation is set up.

    Layout, top to bottom: title, the conversation, the box to type in (always visible). The conversation area is
    created first but filled last, so a question sent in this run already appears in it."""
    if not user.has(RoleName.APPLICANT):
        return
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key=KEY):
        with st.popover("Ask Tarqiya", icon=":material/chat:"):
            size = st.session_state.get(SIZE, "compact")
            width, height, vh = SIZES[size]
            st.markdown(f"<style>div[data-testid='stPopoverBody']{{width:min({width}px,94vw)!important;max-width:96vw!important}}"
                        f"div[data-testid='stVerticalBlock'].st-key-{KEY}_conversation{{max-height:{vh}vh!important}}</style>", unsafe_allow_html=True)
            title, resize = st.columns([6, 1], vertical_alignment="center")
            title.markdown("**Tarqiya assistant**")
            if resize.button("", key=f"{KEY}_size_toggle", icon=":material/open_in_full:" if size == "compact" else ":material/close_fullscreen:",
                             help="Make the chat bigger" if size == "compact" else "Make the chat smaller", type="tertiary"):
                st.session_state[SIZE] = "large" if size == "compact" else "compact"
                st.rerun()
            conversation = st.container(height=height, border=False, key=f"{KEY}_conversation")
            with st.form(f"{KEY}_form", clear_on_submit=True, border=False):
                typed, send = st.columns([5, 1], vertical_alignment="bottom")
                question = typed.text_input("Your question", placeholder="Type your question here...", label_visibility="collapsed",
                                            max_chars=chat.MAX_QUESTION_CHARS)
                sent = send.form_submit_button("", icon=":material/send:", use_container_width=True)
            if sent and question.strip():
                _ask(user, question.strip())
            history = st.session_state.setdefault(HISTORY, [])
            with conversation:
                with st.chat_message("assistant"):
                    st.markdown("Hello. Ask me what is missing from your application, what your track requires, or where your eligibility "
                                "stands. I cannot submit or change anything.")
                for m in history:
                    with st.chat_message(m["role"]):
                        st.markdown(m["content"])
                        if m["role"] == "assistant" and m.get("sections"):
                            _links(m["sections"])
            if history and st.button("Clear conversation", key=f"{KEY}_clear", type="tertiary"):
                st.session_state[HISTORY] = []
                st.rerun()
