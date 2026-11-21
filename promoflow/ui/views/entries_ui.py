"""One panel for every "one document = one entry" evidence type (committee letters, certificates, thesis decisions ...).

The applicant drops several documents (scans work) and presses Read; the preview table shows one row per document, with the reason next
to any problem; every value can be corrected in the table; only the ticked rows are saved, each keeping its own document as evidence.
The same steps as the Section 6 report panels (section6/imports_ui.py), written once for all kinds listed in extraction/entry_docs.py.
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import pandas as pd
import streamlit as st

from promoflow.db.session import session_scope
from promoflow.ui import cache
from promoflow.dossier import doc_entries
from promoflow.extraction import rule_reports
from promoflow.extraction.entry_docs import KINDS, parse_date, read_entries
from promoflow.extraction.local_read import ReadFailed


def _work(kind, name, data, ctx):
    """Runs in a worker thread: no Streamlit calls in here."""
    try:
        return name, read_entries(kind, name, data, ctx), None
    except ReadFailed as e:
        return name, [], str(e)


WHOLE_NUMBERS = ("attendees", "year", "author_position", "total_authors", "h_index", "total_citations")


def _cell(value, col):
    if col.kind == "multi":
        return ", ".join((col.options or {}).get(v, str(v)) for v in (value or []))
    if col.kind == "select":
        return None if value is None else (col.options or {}).get(value, str(value))
    if col.kind == "date":
        return value if isinstance(value, date) else None
    return value


def _back(value, col):
    """The table cell the applicant edited, turned back into the value an entry stores."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if col.kind == "multi":
        reverse = {label: code for code, label in (col.options or {}).items()}
        return [reverse[x.strip()] for x in str(value).split(",") if x.strip() in reverse] or None
    if col.kind == "select":
        reverse = {label: code for code, label in (col.options or {}).items()}
        return reverse.get(value)
    if col.kind == "date":
        # The table gives a date back as a date, a pandas timestamp (a datetime) or, once the applicant has typed into an empty cell, TEXT.
        # An entry stores a plain date, and a datetime or a string cannot be compared with one.
        if isinstance(value, str):
            return parse_date(value)
        return value.date() if isinstance(value, datetime) else value
    if col.kind == "number":
        return int(value) if float(value).is_integer() and col.key in WHOLE_NUMBERS else float(value)
    return value


def _study_years_from_cv(drafts, cv_bytes, problems) -> None:
    """Fill the study start of degree drafts from the CV's Education table (read with pdfplumber)."""
    from promoflow.extraction import entry_docs_more as M

    rows = rule_reports.cv_education(cv_bytes)
    if rows is None:
        problems.append("Your CV: no Education table was found, so the study start was not filled in.")
        return
    M.fill_study_years(drafts, rows)


def panel(kind_key: str, flash_key: str) -> None:
    kind = KINDS[kind_key]
    key = f"ent_{kind_key}"
    user = st.session_state["current_user"]
    with st.container(key=f"auto_{kind_key}", border=True):
        st.caption(f"Automatic upload · {kind.noun}. Upload the documents (PDF or scan) and press Read. Check the table, correct anything, and add. "
                   "Each document is kept as the evidence for its entry.")
        picture = kind_key == "scopus"                 # a screenshot, not a PDF
        uploads = st.file_uploader(f"Documents: {kind.noun}", type=["pdf", "png", "jpg", "jpeg"] if picture else ["pdf"], accept_multiple_files=not picture, key=key + "_files")
        uploads = [uploads] if picture and uploads else uploads
        cv_file = None
        if kind_key == "degree":
            cv_file = st.file_uploader("Your CV (optional): fills the study start, which certificates do not print", type=["pdf"], key=key + "_cv")
        if not uploads:
            return
        digest = hashlib.sha1(b"".join(u.getvalue() for u in uploads) + (cv_file.getvalue() if cv_file else b"")).hexdigest()
        if st.button(f"Read {len(uploads)} document{'s' if len(uploads) != 1 else ''}", icon=":material/auto_fix_high:", type="primary", key=key + "_read"):
            with session_scope() as s:
                ctx = doc_entries.load_ctx(s, user.full_name or "", user.id)
            drafts, problems = [], []
            bar = st.progress(0.0, text="Reading…")
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_work, kind, u.name, u.getvalue(), ctx) for u in uploads]
                for done, f in enumerate(as_completed(futures), 1):
                    name, draft, err = f.result()
                    drafts.extend(draft)
                    if err:
                        problems.append(f"{name}: {err}")
                    bar.progress(done / len(futures), text=f"Read {done} of {len(futures)}")
            bar.empty()
            order = {u.name: i for i, u in enumerate(uploads)}
            drafts.sort(key=lambda d: order.get(d.filename, 0))
            if cv_file is not None:
                _study_years_from_cv(drafts, cv_file.getvalue(), problems)
            doc_entries.precheck(kind_key, drafts, ctx)
            st.session_state[key] = {"digest": digest, "drafts": drafts, "problems": problems, "ctx": ctx}
        state = st.session_state.get(key)
        if not state or state["digest"] != digest:
            return
        for p in state["problems"]:
            st.error(p, icon=":material/error:")
        drafts, ctx = state["drafts"], state["ctx"]
        if not drafts:
            return
        cols = kind.columns(ctx)
        st.caption(f"Read {len(uploads)} document{'s' if len(uploads) != 1 else ''}, {len(drafts)} entr{'ies' if len(drafts) != 1 else 'y'}. "
                   "Rows with a problem start unticked; a \"check:\" note only asks you to look.")
        rows = [{"Add": d.ok, "File": d.filename, **{c.label: _cell(d.values.get(c.key), c) for c in cols},
                 "Read by": {"text": "text (pdfplumber)", "ocr": "scan (OCR)"}.get(d.route, d.route), "Problem": "; ".join(d.issues)} for d in drafts]
        config = {}
        for c in cols:
            if c.kind == "select":
                config[c.label] = st.column_config.SelectboxColumn(options=list((c.options or {}).values()))
            elif c.kind == "date":
                config[c.label] = st.column_config.DateColumn()
            elif c.kind == "number":
                config[c.label] = st.column_config.NumberColumn()
        edited = st.data_editor(pd.DataFrame(rows), hide_index=True, use_container_width=True, key=key + "_table", column_config=config,
                                disabled=["File", "Read by", "Problem"])
        chosen = []
        for d, (_, row) in zip(drafts, edited.iterrows()):
            if row["Add"]:
                for c in cols:
                    d.values[c.key] = _back(row[c.label], c)
                chosen.append(d)
        if st.button(f"Add {len(chosen)} {kind.noun}", type="primary", icon=":material/playlist_add:", key=key + "_add", disabled=not chosen):
            with session_scope() as s:
                report = doc_entries.add_entries(s, user.id, kind_key, chosen, ctx)
            st.session_state.pop(key, None)
            cache.bump_version()                    # the page re-reads its lists even when nothing new was written (entries added from another tab)
            if kind_key == "cv":
                st.session_state.pop("s2_loaded", None)        # Section 2 fills its date box from the database once: let it do so again
            st.session_state[flash_key] = report.describe(kind.noun) + ("" if not report.rejected else " Not added: " + "; ".join(report.rejected[:3]))
            st.rerun()


# ---- the two buttons at the top of every tab: Automatic upload and Manual upload --------------------------------------------------------
#
# Automatic upload: the documents are read on this machine and the entries are filled in for you to check.
# Manual upload:    you type the values yourself (and attach the evidence file).
# The two switch each other on and off, so exactly one of them is open at a time. `new_key` is the session key the tab uses to open its own
# "add" form (K + "editing" set to "new"); a tab with a single document and no list has no such key.

def add_bar(kinds=(), flash_key: str = "", new_key: str | None = None, auto=None, blocked: bool = False, blocked_why: str = "",
            default: str | None = None) -> None:
    ident = new_key or (kinds[0] if kinds else "bar")
    mode_key = f"ab_{ident}"
    manual_open = (st.session_state.get(new_key) == "new") if new_key else (st.session_state.get(mode_key, default) == "manual")
    auto_open = st.session_state.get(mode_key) == "auto"
    has_auto = bool(kinds) or auto is not None
    left, right = st.columns(2)
    if left.button("Automatic upload", icon=":material/auto_fix_high:", key=mode_key + "_auto", use_container_width=True, disabled=not has_auto,
                   type="primary" if auto_open else "secondary",
                   help=None if has_auto else "There is no automatic reading for this type of document yet: use Manual upload."):
        st.session_state[mode_key] = None if auto_open else "auto"
        if new_key:
            st.session_state.pop(new_key, None)
        st.rerun()
    if right.button("Manual upload", icon=":material/edit_note:", key=mode_key + "_manual", use_container_width=True, disabled=blocked,
                    type="primary" if manual_open else "secondary", help=blocked_why or None):
        if new_key:
            if manual_open:
                st.session_state.pop(new_key, None)
            else:
                st.session_state[new_key] = "new"
                st.session_state[mode_key] = "manual"
        else:
            st.session_state[mode_key] = "manual"
        st.rerun()
    if auto_open:
        for kind_key in kinds:
            panel(kind_key, flash_key)
        if auto is not None:
            auto()


# ---- fill a form's own boxes from the document chosen in its uploader --------------------------------------------------
#
# The "Add ..." forms of the sections have a file box. When a file is chosen there, the boxes of the SAME form are filled from it (the same
# reader as the panel above). The boxes' values live in session_state under `prefix + suffix`, so setting them before the boxes are drawn is
# enough. Only a NEW file changes the boxes, so whatever the applicant edits afterwards is kept.

def _forms():
    from promoflow.db import enums as E
    return {
        "degree": ("cert", {"level": ("level", ("enum", E.DegreeLevel)), "specialization": ("spec", "t"), "university": ("uni", "t"), "country_code": ("country", "t"),
                            "study_from": ("from", "d"), "study_to": ("to", "d"), "graduation_date": ("grad", "d"), "thesis_title": ("thesis", "t")}),
        "rank": ("evidence", {"rank": ("rank", ("enum", E.Rank)), "date_obtained": ("obtained", "d"), "university": ("uni", "t"), "country_code": ("country", "t"),
                              "held_from": ("from", "d"), "at_this_university": ("here", "b")}),
        "position": ("evidence", {"position": ("position", "t"), "employer": ("employer", "t"), "country_code": ("country", "t"), "date_from": ("from", "d"), "date_to": ("to", "d")}),
        "paper": ("paper_file", {"title": ("title", "t"), "journal_name": ("journal", "t"), "issn": ("issn", "t"), "publisher": ("publisher", "t"),
                                 "language": ("language", ("enum", E.Language)), "status": ("status", ("enum", E.PublicationStatus)), "issue_date": ("issue_date", "d"),
                                 "volume": ("volume", "t"), "issue": ("issue", "t"), "pages": ("pages", "t"), "total_authors": ("total", "i"), "author_position": ("position", "i"),
                                 "_other_authors": ("others", "lines"), "applicant_role": ("role", ("enum", E.AuthorRole)), "main_author_basis": ("basis", ("enum", E.MainAuthorBasis)),
                                 "at_this_university": ("here", "b")}),
        "acceptance": ("acceptance_file", {"title": ("title", "t"), "journal_name": ("journal", "t"), "issn": ("issn", "t"), "publisher": ("publisher", "t"),
                                           "language": ("language", ("enum", E.Language)), "status": ("status", ("enum", E.PublicationStatus)), "acceptance_date": ("acceptance_date", "d"),
                                           "total_authors": ("total", "i"), "author_position": ("position", "i"), "_other_authors": ("others", "lines"),
                                           "applicant_role": ("role", ("enum", E.AuthorRole)), "main_author_basis": ("basis", ("enum", E.MainAuthorBasis))}),
        "book": ("evidence", {"item_type": ("type", ("enum", E.BookItemType)), "book_title": ("book_title", "t"), "chapter_title": ("chapter_title", "t"), "publisher": ("publisher", "t"),
                              "publication_date": ("pub_date", "d"), "isbn": ("isbn", "t"), "main_or_sole_author": ("main_or_sole", "b"), "from_thesis": ("thesis", "b")}),
        "conference": ("evidence", {"title": ("title", "t"), "conference_title": ("conf_title", "t"), "organizer": ("organizer", "t"), "conference_date": ("date", "d"),
                                    "place": ("place", "t"), "pages": ("pages", "t"), "doi": ("doi", "t"), "main_or_sole_author": ("main_or_sole", "b")}),
        "funded": ("evidence", {"title": ("title", "t"), "funding_body": ("body", "t"), "funder_code": ("funder_type", ("lookup", "funder_type")),
                                "role": ("role", ("enum", E.InvestigatorRole)), "status": ("status", ("enum", E.ProjectStatus)), "amount": ("amount", "n"), "currency": ("currency", "t"),
                                "start_date": ("start", "d"), "end_date": ("end", "d")}),
        "patent": ("evidence", {"title": ("title", "t"), "patent_number": ("number", "t"), "office_code": ("office", ("lookup", "patent_office")),
                                "status": ("status", ("enum", E.PatentStatus)), "grant_date": ("grant_date", "d"), "inventors": ("inventors", "t")}),
        "creative": ("evidence", {"form_code": ("form", ("lookup", "creative_form")), "title": ("title", "t"), "venue": ("venue", "t"),
                                  "organizing_institution": ("org", "t"), "date_from": ("from", "d"), "date_to": ("to", "d"), "approved": ("approved", "b")}),
        "award": ("evidence", {"name": ("name", "t"), "awarding_body": ("body", "t"), "year": ("year", "i"), "scope_code": ("scope", ("lookup", "award_scope"))}),
        "peer_observation": ("evidence", {"course_taught_id": ("course", "course"), "observer_code": ("role", ("lookup", "observer_role")), "observer_name": ("name", "t"),
                                          "observation_date": ("date", "d"), "rating": ("rating", "n"), "scale_max": ("scale", "n")}),
        "innovation": ("evidence", {"type_code": ("type", ("lookup", "innovation_type")), "course_taught_id": ("course", "course"), "description": ("description", "t"),
                                    "measured_outcome": ("outcome", "t")}),
        "policy": ("evidence", {"policy_name": ("name", "t"), "level": ("level", ("enum", E.OrgLevel)), "role_code": ("role", ("lookup", "policy_role")), "activity_date": ("date", "d")}),
        "course_file": ("evidence", {"course_taught_id": ("course", "course"), "is_coordinator": ("coordinator", "b"), "kept_in_code": ("kept_in", ("lookup", "course_file_system")),
                                     "items": ("items", "list")}),
        "letter": ("evidence", {"writer_name": ("name", "t"), "writer_rank": ("rank", "t"), "writer_institution": ("institution", "t"),
                                "relationship_code": ("relationship", ("lookup", "recommendation_relationship"))}),
        "scopus": ("upload", {"h_index": ("h_index", "i"), "total_citations": ("citations", "i"), "screenshot_date": ("date", "d")}),
    }


def _convert(value, conv, ctx):
    """The value in the form a box accepts, or None when it should be left alone."""
    if value is None or value == "":
        return None
    if conv == "t":
        return str(value)
    if conv == "d":
        return value if isinstance(value, date) and date(1960, 1, 1) <= value <= date.today() else None
    if conv == "b":
        return bool(value)
    if conv == "n":
        return float(value)
    if conv == "i":
        return int(value)
    if conv == "list":
        return list(value)
    if conv == "lines":
        return "\n".join(value)
    if conv == "course":
        return value if any(c.id == value for c in ctx.courses) else None
    kind, arg = conv
    if kind == "enum":
        return arg(value)
    return ctx.ids.get(arg, {}).get(value)                      # ("lookup", list_code): a code -> the id the box uses


def _chosen_file(key: str):
    """The file currently chosen in the file box with this key (the box keeps it in session_state), or None."""
    return st.session_state.get(key)


def autofill(kind_key: str, prefix: str) -> None:
    """Call at the top of a form (before its boxes): reads the file chosen in the form's file box once and fills the boxes from it."""
    upload_suffix, mapping = _forms()[kind_key]
    upload = _chosen_file(prefix + upload_suffix)
    state_key = prefix + "af_" + kind_key
    if upload is None:
        st.session_state.pop(state_key, None)
        return
    digest = hashlib.sha1(upload.getvalue()).hexdigest()
    found = st.session_state.get(state_key)
    if found is None or found["digest"] != digest:
        found = {"digest": digest, "error": None, "issues": []}
        user = st.session_state["current_user"]
        with st.spinner("Reading the document…"):
            with session_scope() as s:
                ctx = doc_entries.load_ctx(s, user.full_name or "", user.id)
            try:
                drafts = read_entries(KINDS[kind_key], upload.name, upload.getvalue(), ctx)
            except ReadFailed as e:
                found["error"] = str(e)
            else:
                draft = drafts[0]
                for key, (suffix, conv) in mapping.items():
                    value = _convert(draft.values.get(key), conv, ctx)
                    if value is not None:
                        st.session_state[prefix + suffix] = value
                found["issues"] = [i for i in draft.issues if i.startswith("check:")] + [i for i in draft.issues if not i.startswith("check:")]
        st.session_state[state_key] = found
    if found["error"]:
        st.warning(found["error"], icon=":material/description:")
    else:
        st.info("We filled the boxes below from the document. Please check every value." + ("" if not found["issues"] else " Still to do: " + "; ".join(found["issues"]) + "."),
                icon=":material/auto_fix_high:")
