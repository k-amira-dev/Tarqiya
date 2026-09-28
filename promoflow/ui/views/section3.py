"""Section 3 – Academic Degrees & Equivalency (spec chapter 7)."""
from datetime import date

import streamlit as st

from promoflow.countries import COUNTRY_CODES, country_name
from promoflow.db.enums import DegreeLevel
from promoflow.db.session import session_scope
from promoflow.dossier import section3 as s3
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import theme

K = "s3_"
LEVEL_LABEL = {DegreeLevel.BACHELOR: "Bachelor", DegreeLevel.MASTER: "Master", DegreeLevel.PHD: "PhD",
              DegreeLevel.OTHER_DOCTORATE: "Other doctorate"}


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    with session_scope() as s:
        ctx = s3.load(s, user.id, today)

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 3 OF 11</div>
    <h1>Academic Degrees &amp; Equivalency</h1>
    <p>One entry per degree, matching the "Academic Degrees Earned" table of the application form.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 3 is read-only.", icon=":material/lock:")
    elif not s3.has_doctorate(ctx.degrees):
        st.warning("At least one PhD (or equivalent doctorate) entry is required.", icon=":material/warning:")

    editing = st.session_state.get(K + "editing")
    for row in ctx.degrees:
        if editing == row.degree.id:
            _entry_form(ctx.case_id, today, editable, row)
        else:
            _entry_summary(row, editable)

    if editable:
        if editing == "new":
            _entry_form(ctx.case_id, today, editable, None)
        else:
            if st.button("+ Add a degree", key="s3_add", use_container_width=False):
                st.session_state[K + "editing"] = "new"
                st.rerun()


def _entry_summary(row: s3.DegreeRow, editable: bool) -> None:
    d = row.degree
    with st.container(key=f"card_degree_{d.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(LEVEL_LABEL[d.level])} · {theme.esc(d.specialization)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(d.university)}, {theme.esc(country_name(d.country_code))}
            · graduated {d.graduation_date:%b %Y}{" · thesis: " + theme.esc(d.thesis_title) if d.thesis_title else ""}</div>""")
            missing = []
            if row.certificate is None:
                missing.append("degree certificate")
            if d.equivalency_required and row.equivalency_certificate is None:
                missing.append("equivalency certificate")
            if missing:
                theme.html(f'<div class="pf-note">Missing: {theme.esc(", ".join(missing))}.</div>')
        with b:
            if editable:
                if st.button("Edit", key=f"s3_edit_{d.id}", use_container_width=True):
                    st.session_state[K + "editing"] = d.id
                    st.rerun()
                if st.button("Delete", key=f"s3_del_{d.id}", use_container_width=True):
                    with session_scope() as s:
                        s3.delete(s, st.session_state["current_user"].id, d.id)
                    st.session_state[K + "flash"] = "Degree removed."
                    st.rerun()


def _entry_form(case_id: int, today: date, editable: bool, row: "s3.DegreeRow | None") -> None:
    d = row.degree if row else None
    prefix = f"s3_f_{d.id if d else 'new'}_"
    with st.container(key=f"card_degree_form_{d.id if d else 'new'}"):
        theme.card_header("+", "Edit degree" if d else "Add a degree")
        a, b = st.columns(2)
        level = a.selectbox("Degree level", list(DegreeLevel), format_func=LEVEL_LABEL.get,
                            index=list(DegreeLevel).index(d.level) if d else None,
                            placeholder="Choose a level", key=prefix + "level")
        specialization = b.text_input("Specialization", value=d.specialization if d else "", key=prefix + "spec")
        c, e = st.columns(2)
        university = c.text_input("University", value=d.university if d else "", key=prefix + "uni")
        country_code = e.selectbox("Country", COUNTRY_CODES, format_func=country_name,
                                   index=COUNTRY_CODES.index(d.country_code) if d else None,
                                   placeholder="Choose a country", key=prefix + "country")
        f, g = st.columns(2)
        study_from = f.date_input("Study period – from", value=d.study_from if d else None,
                                  min_value=date(1960, 1, 1), max_value=today, format="DD/MM/YYYY",
                                  key=prefix + "from", help="Only the month and year are used.")
        study_to = g.date_input("Study period – to", value=d.study_to if d else None,
                                min_value=date(1960, 1, 1), max_value=today, format="DD/MM/YYYY",
                                key=prefix + "to", help="Only the month and year are used.")
        h, i = st.columns(2)
        graduation_date = h.date_input("Date of graduation", value=d.graduation_date if d else None,
                                       min_value=date(1960, 1, 1), max_value=today, format="DD/MM/YYYY",
                                       key=prefix + "grad")
        if level in (DegreeLevel.MASTER, DegreeLevel.PHD):
            thesis_title = i.text_input("Thesis / dissertation title", value=(d.thesis_title if d else "") or "",
                                        key=prefix + "thesis")
        else:
            thesis_title = None
            i.empty()

        cert_label = "Degree certificate" if row is None or row.certificate is None else "Replace degree certificate"
        cert_upload = st.file_uploader(cert_label, type=["pdf", "jpg", "jpeg", "png"], key=prefix + "cert")

        equivalency_required = st.toggle("Equivalency required for this degree", value=bool(d.equivalency_required) if d else False,
                                         key=prefix + "equiv_req")
        equivalency_upload = None
        if equivalency_required:
            equiv_label = ("Equivalency certificate" if row is None or row.equivalency_certificate is None
                          else "Replace equivalency certificate")
            equivalency_upload = st.file_uploader(equiv_label, type=["pdf", "jpg", "jpeg", "png"],
                                                  key=prefix + "equiv_file")

        values = {
            "level": level, "specialization": specialization.strip(), "university": university.strip(),
            "country_code": country_code, "study_from": study_from, "study_to": study_to,
            "graduation_date": graduation_date, "thesis_title": (thesis_title or "").strip() or None,
            "equivalency_required": equivalency_required,
        }
        cert_tuple = (cert_upload.name, cert_upload.getvalue()) if cert_upload is not None else None
        equiv_tuple = (equivalency_upload.name, equivalency_upload.getvalue()) if equivalency_upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save degree", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s3.validate_degree(values, row.certificate is not None if row else False, today,
                                        cert_tuple, equiv_tuple,
                                        row.equivalency_certificate is not None if row else False)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                           + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if d is None:
                    s3.add(s, user_id, values, cert_tuple, equiv_tuple)
                else:
                    s3.update(s, user_id, d.id, values, cert_tuple, equiv_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state[K + "flash"] = "Degree saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
