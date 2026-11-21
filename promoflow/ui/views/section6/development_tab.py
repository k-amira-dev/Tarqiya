"""6I · Teaching-development activity attended — the tab inside the Section 6 (Teaching & Academic
Advising) page."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.enums import ActivityFormat
from promoflow.db.session import session_scope
from promoflow.dossier.section6 import development as s6i
from promoflow.ui import theme
from promoflow.ui.views.section6.lookups import development_topic_options

K = "s6i_"
FORMAT_LABEL = {ActivityFormat.WORKSHOP: "Workshop", ActivityFormat.SEMINAR: "Seminar",
               ActivityFormat.CONFERENCE: "Conference"}


def render(rows: list[s6i.DevelopmentRow], editable: bool) -> None:
    if editable:
        entries_ui.add_bar(["development"], "s6_flash", K + "editing")
    theme.html('<div class="pf-note">Activities you organised or delivered (rather than attended) go in '
              "§7A-3 (service) instead.</div>")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.activity.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)


def _summary(row: s6i.DevelopmentRow, editable: bool) -> None:
    d = row.activity
    topics = {o.id: o.label for o in development_topic_options()}
    with st.container(key=f"card_development_{d.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(d.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{FORMAT_LABEL[d.format]} ·
            {theme.esc(topics.get(d.topic_id, ""))} · {d.activity_date:%d %b %Y}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6i_edit_{d.id}", use_container_width=True):
                    st.session_state[K + "editing"] = d.id
                    st.rerun()
                if st.button("Delete", key=f"s6i_del_{d.id}", use_container_width=True):
                    with session_scope() as s:
                        s6i.delete(s, st.session_state["current_user"].id, d.id)
                    st.session_state["s6_flash"] = "Activity removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s6i.DevelopmentRow | None") -> None:
    d = row.activity if row else None
    prefix = f"s6i_f_{d.id if d else 'new'}_"
    today = date.today()
    topics = development_topic_options()
    topic_ids = [t.id for t in topics]
    topic_labels = {t.id: t.label for t in topics}
    with st.container(key=f"card_development_form_{d.id if d else 'new'}"):
        theme.card_header("+", "Edit activity" if d else "Add a development activity")
        title = st.text_input("Title", value=d.title if d else "", key=prefix + "title")
        a, b = st.columns(2)
        format_ = a.selectbox("Type", list(ActivityFormat), format_func=FORMAT_LABEL.get,
                              index=list(ActivityFormat).index(d.format) if d else None,
                              placeholder="Choose a type", key=prefix + "format")
        topic_id = b.selectbox("Topic", topic_ids, format_func=topic_labels.get,
                               index=topic_ids.index(d.topic_id) if d else None,
                               placeholder="Choose a topic", key=prefix + "topic")
        c, e = st.columns(2)
        organizer = c.text_input("Organizer", value=d.organizer if d else "", key=prefix + "organizer")
        activity_date = e.date_input("Date", value=d.activity_date if d else None, min_value=date(1970, 1, 1),
                                     max_value=today, format="DD/MM/YYYY", key=prefix + "date")
        hours = st.number_input("Hours (optional)", min_value=0.0, step=0.5, value=float(d.hours) if d and d.hours else 0.0,
                                key=prefix + "hours")
        label = "Certificate" if row is None or row.certificate is None else "Replace certificate"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "certificate")

        values = {"title": title.strip(), "format": format_, "topic_id": topic_id, "organizer": organizer.strip(),
                 "activity_date": activity_date, "hours": hours or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6i.validate(values, today, row.certificate is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if d is None:
                    s6i.add(s, user_id, values, upload_tuple)
                else:
                    s6i.update(s, user_id, d.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Activity saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
