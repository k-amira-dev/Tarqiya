"""Section 11 – Review & Submit (spec chapter 13)."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier import section11 as s11
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import theme

K = "s11_"
ICON = {"ok": "✓", "warn": "!", "fail": "✕", "info": "i"}


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    with session_scope() as s:
        ctx = s11.load(s, user.id, today)

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 11 OF 11</div>
    <h1>Review &amp; Submit</h1>
    <p>Check everything below before you submit. Submission locks the dossier and starts the review workflow.</p>
    </div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if ctx.status not in EDITABLE:
        theme.html(f'<div class="pf-note">Case status: <b>{theme.esc(ctx.status.value.replace("_", " ").title())}'
                  "</b>. The dossier is locked.</div>")
        return

    _completeness_card(ctx)
    _eligibility_card(ctx)
    if ctx.research is not None:
        _research_card(ctx)
    _submit_card(ctx, user.id, today)


def _completeness_card(ctx: s11.Section11Context) -> None:
    with st.container(key="card_completeness"):
        theme.card_header("✓", "Completeness", f"{ctx.completed_count} of {len(ctx.sections)} required sections complete.")
        rows = ""
        for row in ctx.sections:
            status = "ok" if row.complete else "fail"
            detail = row.note or "Complete."
            rows += (f'<div class="pf-check"><div class="ic {status}">{ICON[status]}</div>'
                    f'<div><b>§{row.code} · {theme.esc(row.title)}</b><small>{theme.esc(detail)}</small></div></div>')
        theme.html(rows)


def _eligibility_card(ctx: s11.Section11Context) -> None:
    with st.container(key="card_eligibility_preview"):
        theme.card_header("i", "Preliminary eligibility",
                          "This is information for the applicant, not a decision. The Eligibility Checker "
                          "confirms everything on submission.")
        rows = "".join(
            f'<div class="pf-check"><div class="ic {c.status}">{ICON[c.status]}</div><div><b>{theme.esc(c.label)}</b>'
            f'<small>{theme.esc(c.detail)}{" · " + theme.esc(c.policy_ref) if c.policy_ref else ""}</small></div></div>'
            for c in ctx.eligibility_checks)
        theme.html(rows)


def _research_card(ctx: s11.Section11Context) -> None:
    r = ctx.research
    with st.container(key="card_research_snapshot"):
        theme.card_header("5A", "Research counts (preview)",
                          "Simple counts from Section 5, not the full Research Agent check (caps and "
                          "cross-checks aren't applied yet).")
        rows = [
            ("Total papers submitted", r.total_papers, r.min_total_publications),
            ("Sole / main-author papers", r.sole_or_main, r.min_sole_main_author),
            ("Published papers", r.published, r.min_published),
            ("At this institution", r.at_institution, r.min_at_institution),
            ("Class A (sole/main author)", r.class_a_sole_or_main, r.min_class_a_main_author),
        ]
        html_rows = "".join(
            f'<div class="pf-check"><div class="ic {"ok" if have >= need else "warn"}">{ICON["ok" if have >= need else "warn"]}</div>'
            f'<div><b>{theme.esc(label)}</b><small>{have} of {need} required</small></div></div>'
            for label, have, need in rows)
        theme.html(html_rows)


def _submit_card(ctx: s11.Section11Context, user_id: int, today: date) -> None:
    with st.container(key="card_submit"):
        theme.card_header("→", "Submission window", ctx.window_label)
        if not ctx.window_open:
            st.info("Submit is enabled only in the first week of January, April or October.",
                    icon=":material/event_busy:")
        declared = st.checkbox(
            "I confirm the information in this dossier is accurate and complete, and I have signed the "
            "declarations in Section 1.", key=K + "declare", disabled=not ctx.can_submit)
        submit_disabled = not (ctx.can_submit and declared)
        if st.button("Submit application", type="primary", icon=":material/send:", key=K + "submit",
                    disabled=submit_disabled, use_container_width=True):
            try:
                with session_scope() as s:
                    s11.submit(s, user_id, today)
            except s11.CaseLocked as e:
                st.error(str(e))
                return
            st.session_state[K + "flash"] = "Application submitted."
            st.rerun()
        if not ctx.can_submit:
            st.caption("Complete every required section and wait for a submission window to enable this button.")
