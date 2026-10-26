"""End-to-end flows through the real Streamlit pages, using Streamlit's headless AppTest."""
from datetime import date

from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
from promoflow.db.models import PromotionCase
from tests.conftest import TEST_PASSWORD


def page_text(at) -> str:
    return " ".join(m.value for m in at.markdown)


def app():
    return AppTest.from_file("../app/Home.py", default_timeout=30)


def login(at, email, password=TEST_PASSWORD):
    at.text_input[0].input(email)
    at.text_input[1].input(password)
    at.button[0].click()
    return at.run()


def complete_profile(at, employee_id):
    at.text_input[1].input(employee_id)
    at.button[0].click()
    return at.run()


def test_wrong_password_shows_error(app_env):
    at = login(app().run(), "applicant@promoflow.test", "wrong")
    assert "Incorrect email or password." in [e.value for e in at.error]


def test_login_profile_dashboard_logout(app_env):
    at = app().run()
    assert "Welcome to PromoFlow" in page_text(at)
    at = login(at, "applicant@promoflow.test")
    assert "Complete your profile" in page_text(at)
    at = complete_profile(at, "E-1001")
    assert "How PromoFlow works" in page_text(at)          # the first page is the overview, for anyone new
    assert "The promotion in six steps" in page_text(at)
    [b for b in at.button if "dashboard" in b.label.lower()][0].click()
    at = at.run()
    assert "Welcome back, Test" in page_text(at)
    assert "Your application" in page_text(at)
    at.sidebar.button(key="logout").click()
    at = at.run()
    assert "Welcome to PromoFlow" in page_text(at)


def test_hod_sees_both_zones(app_env):
    at = complete_profile(login(app().run(), "hod.cs@promoflow.test"), "E-2001")
    sidebar = " ".join(m.value for m in at.sidebar.markdown)
    assert "My promotion" in sidebar and "Reviews" in sidebar  # a Head of Department is also an applicant


def test_dashboard_opens_section0(app_env):
    at = complete_profile(login(app().run(), "applicant@promoflow.test"), "E-1001")
    [b for b in at.button if "Section 0" in b.label][0].click()  # dashboard → Section 0, as a user would
    at = at.run()
    assert "Applicant Details" in page_text(at)


def section0_page(app_env):
    """Section 0 on its own (AppTest does not keep the current page of st.navigation between reruns)."""
    from promoflow.ui.auth import _load  # noqa: PLC0415  (reloaded by the fixture)
    from promoflow.auth.service import create_session  # noqa: PLC0415
    from promoflow.db.models import User  # noqa: PLC0415
    with app_env.session_scope() as s:
        token = create_session(s, s.scalar(select(User).where(User.email == "applicant@promoflow.test")))
    script = "from promoflow.ui import theme\nfrom promoflow.ui.views import section0\ntheme.inject()\nsection0.render()\n"
    at = AppTest.from_string(script, default_timeout=30)
    at.session_state["current_user"] = _load(token)
    return at.run()


def test_section0_validation_and_save(app_env):
    at = section0_page(app_env)
    assert "Applicant Details" in page_text(at)
    assert "Choose your promotion track" in page_text(at)  # preview before a track is chosen

    at.button(key="s0_save").click()
    at = at.run()
    assert "Please fix the following" in page_text(at)  # an empty form is rejected

    at.radio(key="s0_track").set_value(PromotionTrack.TO_ASSOCIATE)
    at.text_input(key="s0_specialization").input("Computer Science")
    at.text_input(key="s0_fine_specialization").input("Machine Learning")
    at.date_input(key="s0_appointment_date").set_value(date(2019, 9, 1))
    at.selectbox(key="s0_rank_on_appointment").set_value(Rank.ASSISTANT_PROFESSOR)
    at.date_input(key="s0_current_rank_date").set_value(date(2019, 9, 1))
    at.text_input(key="s0_scopus_author_id").input("57193456789")
    at.button(key="s0_save").click()
    at = at.run()
    assert "Section 0 saved." in [x.value for x in at.success]
    assert "Time in current rank" in page_text(at)
    with app_env.session_scope() as s:
        case = s.scalar(select(PromotionCase))
        assert case.status == CaseStatus.DRAFT and case.specialization == "Computer Science"
