"""Seed reference data and development accounts.

    python -m promoflow.db.seed            # everything (PostgreSQL, after `alembic upgrade head`)
    python -m promoflow.db.seed --auth-only  # colleges, departments, users (also works on SQLite)
    python -m promoflow.db.seed --demo-journals  # DEVELOPMENT ONLY: six fictional journals with rankings

Idempotent: running it twice does not create duplicates.

WHY SEED? (for beginners)
`alembic upgrade head` creates EMPTY tables. The system also needs some starting data to be usable: the policy
thresholds, the two scoring rubrics, the dropdown lists, and (for development only) fictional test accounts. This script
inserts them. 'Seeding' means 'planting the starting data'.
"""
import argparse
import os
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.auth.passwords import hash_password
from promoflow.db.enums import AuthProvider, PromotionTrack, RoleName, RubricCode
from promoflow.db.models import (
    College, Department, Journal, JournalRanking, LookupValue, PolicyVersion, PromotionCriteria, ResearchItemCap, Rubric, RubricItem,
    User, UserRole,
)
from promoflow.db.session import session_scope

# The version of the promotion policy these numbers come from. A case is judged by the policy version in force when
# it was submitted, so a new policy can be added later without changing old cases.
POLICY_CODE = "SCHESR-2026-05"

# Conditions document §1, §2, §6, §7 (policy briefing V3, May 2026).
# All numeric thresholds, one block per promotion track (minimum years in rank, minimum papers, and so on). They
# live in the database, not in the code, so they can change without editing Python.
CRITERIA = {
    PromotionTrack.TO_ASSOCIATE: dict(
        min_years_in_rank=5, min_years_at_institution=1, early_application_months=4, exceptional_min_years=4,
        reapply_min_years=1, reapply_new_publications=2, reapply_new_class_a=1, reapply_new_main_author=1,
        min_total_publications=6, min_sole_main_author=3, min_published=3, min_at_institution=2,
        min_class_a_main_author=2, max_supervision_rule_papers=2, max_books_total=2, max_patents=2,
        max_creative_works=2, min_referee_reports=3, min_referee_average_pct=Decimal("75"),
    ),
    PromotionTrack.TO_FULL: dict(
        min_years_in_rank=5, min_years_at_institution=2, early_application_months=4, exceptional_min_years=4,
        reapply_min_years=1, reapply_new_publications=3, reapply_new_class_a=2, reapply_new_main_author=2,
        min_total_publications=9, min_sole_main_author=5, min_published=5, min_at_institution=4,
        min_class_a_main_author=3, max_supervision_rule_papers=3, max_books_total=3, max_patents=3,
        max_creative_works=3, min_referee_reports=3, min_referee_average_pct=Decimal("80"),
    ),
}

# p.6 – per-type book caps (same for both tracks); combined cap is max_books_total above.
BOOK_CAPS = [("knowledge_contribution", 2, None), ("specialized", 1, None), ("textbook", 1, None),
             ("heritage", 1, "class_b")]

# Appendix E – Teaching & Academic Advising Evaluation Form (30 points, pass 24).
# One tuple per line of the form: (item number, text, minimum points, maximum points, Full-Professor-only?, can its
# points be redistributed?).
TEACHING_ITEMS = [
    (1, "Effectiveness of teaching according to students' evaluations", 2, 4, False, False),
    (2, "Effectiveness of teaching according to peer evaluations of a sample of courses", 2, 4, False, False),
    (3, "Diversity of courses taught", 2, 2, False, False),
    (4, "Maintaining and updating course files", 3, 3, False, False),
    (5, "Contribution to graduate studies (graduate courses and/or thesis supervision)", 0, 3, True, False),
    (6, "Developing study plans and programs, proposing or modifying courses", 3, 5, False, False),
    (7, "Case studies comparing the effectiveness of teaching methods", 2, 2, False, False),
    (8, "Utilizing educational technologies in teaching", 4, 4, False, False),
    (9, "Participating in academic advising", 4, 4, False, True),
    (10, "Seminars, workshops or conferences on improving teaching methods", 1, 2, False, False),
]

# Appendix F – University & Community Service Evaluation Form (10 points).
SERVICE_ITEMS = [
    (1, "Serving on department, college and university committees", 4, 6, False, False),
    (2, "Activities of local, regional and international academic and professional associations", 0, 2, False, False),
    (3, "Training and educational activities inside and outside the university", 0, 2, False, False),
    (4, "Organizing or lecturing in workshops and seminars of the department, college or university", 0, 2, False, False),
    (5, "Academic or professional consultation in the field of specialization", 0, 2, False, False),
]
# The form says "80% (i.e. 7 points out of 10)"; 80% of 10 is 8. Kept as a setting until confirmed.
SERVICE_PASS_POINTS = Decimal(os.getenv("SERVICE_PASS_POINTS", "8"))

# Spec §15 – admin-editable dropdown lists: list_code -> [(code, English label), ...]
# Dropdown lists the application forms show (committee roles, activity types, ...). Stored as rows so an admin can
# edit them later; the code refers to them by `code`, never by display text.
LOOKUPS = {
    "committee_role": [("member", "Member"), ("chair", "Chair"), ("secretary", "Secretary"),
                       ("rapporteur", "Rapporteur")],
    "observer_role": [("peer", "Peer faculty member"), ("hod", "Head of Department"),
                      ("tl_centre", "Teaching & learning centre"), ("other", "Other")],
    "admin_position": [("hod", "Head of Department"), ("vice_dean", "Assistant / Vice Dean"), ("dean", "Dean"),
                       ("program_coordinator", "Program coordinator"), ("unit_director", "Centre / unit director"),
                       ("other", "Other")],
    "policy_role": [("drafted", "Drafted"), ("reviewed", "Reviewed"), ("chaired", "Chaired the drafting committee")],
    "curriculum_contribution_type": [("new_course", "Proposed a new course"),
                                     ("modified_course", "Modified an existing course"),
                                     ("study_plan", "Developed a study plan"),
                                     ("program", "Developed or revised a program")],
    "course_change": [("textbook", "Textbook replaced"), ("objectives", "Objectives / learning outcomes changed"),
                      ("chapters", "Chapters added or removed"), ("assessment", "Assessment methods changed"),
                      ("other", "Other")],
    "course_file_system": [("taskstream", "TaskStream"), ("blackboard", "Blackboard"), ("other", "Other")],
    "course_file_item": [("syllabus", "Syllabus"), ("clo_assessment", "Course learning outcome assessment"),
                         ("course_report", "Course report and analysis"), ("improvement_plan", "Improvement plan"),
                         ("student_work", "Samples of student work")],
    "innovation_type": [("case_study", "Case study comparing teaching methods"),
                        ("edtech", "Educational technology"), ("active", "Active learning"),
                        ("blended", "Blended learning"), ("collaborative", "Collaborative learning"),
                        ("ai_tool", "AI-enabled tool (within policy)")],
    "development_topic": [("methods", "Teaching methods"), ("assessment", "Assessment"),
                          ("lms", "Blackboard / LMS"), ("taskstream", "TaskStream"), ("ai", "AI in teaching"),
                          ("other", "Other")],
    "community_activity_type": [("school", "School workshop or lecture"), ("library", "Library workshop or lecture"),
                                ("public_lecture", "Public lecture"), ("funded_company", "Funded project with a company"),
                                ("funded_government", "Funded project with government"),
                                ("funded_university", "Funded project with another university"),
                                ("media_tv", "Media appearance (TV)"), ("media_radio", "Media appearance (radio)"),
                                ("media_press", "Media appearance (press or online)"),
                                ("volunteering", "Volunteering"), ("other", "Other")],
    "funder_type": [("internal", "This university (internal)"), ("government", "Government"),
                    ("company", "Company (industry)"), ("university", "Another university"),
                    ("international", "International agency")],
    "patent_office": [("uspto", "USPTO"), ("epo", "EPO"), ("uae_moe", "UAE Ministry of Economy"),
                      ("wipo", "WIPO (PCT)"), ("other", "Other")],
    "creative_form": [("exhibition", "Exhibition"), ("performance", "Performance"), ("design", "Design work"),
                      ("media", "Media production"), ("other", "Other")],
    "award_scope": [("institutional", "Institutional"), ("national", "National"), ("regional", "Regional"),
                    ("international", "International")],
    "recommendation_relationship": [("colleague", "Colleague"), ("collaborator", "Collaborator"),
                                    ("former_supervisor", "Former supervisor"), ("head_of_unit", "Head of unit"),
                                    ("other", "Other")],
    "publisher_type": [("university", "University"), ("association", "Academic association"),
                       ("research_centre", "Research centre"),
                       ("international_publisher", "Reputable international publisher")],
}

# DEVELOPMENT ONLY: fictional journals (invented names and ISSNs, none refers to a real journal) with a 2025 ranking, so
# the demo applicant's papers can be classified as Class A or B. Real rankings are imported by an admin later.
# (title, issn, publisher, scopus source id, listed in ISI, SJR category, SJR percentile, quartile, impact factor)
DEMO_JOURNALS = [
    ("Journal of Applied Machine Intelligence", "2601-4821", "Meridian Academic Press (fictional)", "SIM-0001", True,
     "Computer Science Applications", "94", 1, "4.2"),
    ("Transactions on Educational Data Science", "2602-1735", "Harbor Scholarly Publishing (fictional)", "SIM-0002",
     True, "Computer Science Applications", "90", 1, "3.8"),
    ("Journal of Intelligent Learning Systems", "2603-9054", "Northgate Journals (fictional)", "SIM-0003", True,
     "Artificial Intelligence", "96", 1, "5.1"),
    ("International Journal of Computational Education", "2604-3318", "Meridian Academic Press (fictional)", "SIM-0004",
     False, "Education", "58", 2, "1.9"),
    ("Journal of Digital Pedagogy", "2605-7762", "Lakeside University Press (fictional)", "SIM-0005", False,
     "Education", "41", 3, "1.2"),
    ("Software Engineering Education Review", "2606-5540", "Harbor Scholarly Publishing (fictional)", "SIM-0006", False,
     "Software", "33", 3, "0.9"),
]

# Fictional organisation for development only.
DEV_COLLEGES = [("COMP", "College of Computing and Informatics", [("CS", "Computer Science"),
                                                                   ("IS", "Information Systems")]),
                ("ENG", "College of Engineering", [("EE", "Electrical Engineering")])]

# Fictional test accounts for development only. They are created by seed_org_and_users(); real accounts are made
# with `python -m promoflow.admin create-user`.
DEV_USERS = [  # email, full name, department code, roles [(role, scope)]
    ("applicant@promoflow.test", "Test Applicant", "CS", [(RoleName.APPLICANT, None)]),
    ("hod.cs@promoflow.test", "Test Head of CS", "CS", [(RoleName.APPLICANT, None), (RoleName.HOD, "CS")]),
    ("dean.comp@promoflow.test", "Test Dean of Computing", "CS", [(RoleName.DEAN, "COMP")]),
    ("chancellor@promoflow.test", "Test Chancellor", None, [(RoleName.CHANCELLOR, None)]),
    ("admin@promoflow.test", "Test Admin", None, [(RoleName.ADMIN, None)]),
]


# Find a row matching `lookup`; if there is none, create it with `values`. This is what makes the seed safe to run
# twice: the second run finds everything and adds nothing.
def _get_or_create(s: Session, model, lookup: dict, **values):
    obj = s.scalar(select(model).filter_by(**lookup))
    if obj is None:
        obj = model(**lookup, **values)
        s.add(obj)
        s.flush()
    return obj


# Create the fictional colleges, departments and test accounts, with their roles (a HoD is tied to one department, a
# Dean to one college).
def seed_org_and_users(s: Session, password: str) -> None:
    depts = {}
    for c_code, c_name, dept_list in DEV_COLLEGES:
        college = _get_or_create(s, College, {"code": c_code}, name_en=c_name)
        for d_code, d_name in dept_list:
            depts[d_code] = _get_or_create(s, Department, {"code": d_code}, name_en=d_name, college_id=college.id)
    colleges = {c.code: c for c in s.scalars(select(College))}

    for email, name, dept_code, roles in DEV_USERS:
        dept = depts.get(dept_code)
        user = _get_or_create(
            s, User, {"email": email}, auth_provider=AuthProvider.LOCAL, password_hash=hash_password(password),
            full_name=name, department_id=dept.id if dept else None, college_id=dept.college_id if dept else None,
        )
        for role, scope in roles:
            scope_kw = {}
            if role == RoleName.HOD:
                scope_kw["department_id"] = depts[scope].id
            if role == RoleName.DEAN:
                scope_kw["college_id"] = colleges[scope].id
            _get_or_create(s, UserRole, {"user_id": user.id, "role": role, **scope_kw})


# Create the policy version, its thresholds and caps, the two rubrics with their items, and the dropdown lists.
def seed_reference(s: Session) -> None:
    policy = _get_or_create(
        s, PolicyVersion, {"code": POLICY_CODE},
        title="Faculty Promotion Policy – SCHESR – May 2026 (briefing V3)", effective_from=date(2026, 5, 1),
    )
    for track, values in CRITERIA.items():
        _get_or_create(s, PromotionCriteria, {"policy_version_id": policy.id, "track": track}, **values)
        for item_type, max_count, cls in BOOK_CAPS:
            _get_or_create(s, ResearchItemCap, {"policy_version_id": policy.id, "track": track, "item_type": item_type},
                           max_count=max_count, counts_as_class=cls)

    for code, title, total, pass_points, items in [
        (RubricCode.TEACHING, "Teaching & Academic Advising Evaluation Form (Appendix E)", 30, Decimal("24"),
         TEACHING_ITEMS),
        (RubricCode.SERVICE, "University & Community Service Evaluation Form (Appendix F)", 10, SERVICE_PASS_POINTS,
         SERVICE_ITEMS),
    ]:
        rubric = _get_or_create(s, Rubric, {"policy_version_id": policy.id, "code": code},
                                title=title, total_points=Decimal(total), pass_points=pass_points)
        for no, text, lo, hi, full_only, redistributable in items:
            _get_or_create(s, RubricItem, {"rubric_id": rubric.id, "item_no": no}, text_en=text,
                           min_points=Decimal(lo), max_points=Decimal(hi), full_professor_only=full_only,
                           redistributable=redistributable)

    for list_code, values in LOOKUPS.items():
        for order, (code, label) in enumerate(values):
            _get_or_create(s, LookupValue, {"list_code": list_code, "code": code}, label_en=label, sort_order=order)


# Entry point when the file is run as a program (python -m promoflow.db.seed).
def seed_demo_journals(s: Session) -> None:
    """DEVELOPMENT ONLY. Add the fictional journals and their 2025 rankings (safe to run twice)."""
    for title, issn, publisher, source_id, isi, category, percentile, quartile, impact in DEMO_JOURNALS:
        journal = _get_or_create(s, Journal, {"issn": issn}, title=title, publisher=publisher,
                                 scopus_source_id=source_id, isi_listed=isi)
        _get_or_create(s, JournalRanking, {"journal_id": journal.id, "year": 2025, "sjr_category": category},
                       scopus_indexed=True, sjr_percentile=Decimal(percentile), quartile=quartile,
                       impact_factor=Decimal(impact))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--auth-only", action="store_true", help="only colleges, departments and dev users")
    parser.add_argument("--demo-journals", action="store_true",
                        help="DEVELOPMENT ONLY: add six fictional journals with rankings, nothing else")
    args = parser.parse_args()
    if args.demo_journals:
        with session_scope() as s:
            seed_demo_journals(s)
        print(f"Added {len(DEMO_JOURNALS)} fictional journals with 2025 rankings.")
        return
    password = os.getenv("DEV_PASSWORD", "promoflow-dev")
    with session_scope() as s:
        seed_org_and_users(s, password)
        if not args.auth_only:
            seed_reference(s)
    print(f"Seeded. Dev accounts use the password from DEV_PASSWORD (default '{password}'):")
    for email, *_ in DEV_USERS:
        print("  ", email)


if __name__ == "__main__":
    main()
