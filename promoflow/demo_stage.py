"""Stage ready-made cases for a live demo, so nobody waits for the agents on stage.

Each demo case is a copy of one real dossier (default: the active case of samira.altamimi@promoflow.test) owned by
its own demo account, then pushed through the REAL pipeline up to the gate it should be waiting at:

    demo.hod@       waits for the Head of Department   (report ready)
    demo.dean@      waits for the Dean                 (Head already approved)
    demo.chancellor@ waits for the Chancellor          (Head and Dean approved, shortlist ready)
    demo.live@      a complete draft, ready to submit live (the agents then run in the background)

Run from the project folder (every command is safe to repeat; a case that is already at its stage is left alone):

    .venv\\Scripts\\python.exe -m promoflow.demo_stage status
    .venv\\Scripts\\python.exe -m promoflow.demo_stage stage [hod|dean|chancellor|live ...]
    .venv\\Scripts\\python.exe -m promoflow.demo_stage reset [hod|dean|chancellor|live ...]

`reset` deletes ONLY the named demo accounts (all four by default), with their cases.
The demo accounts get the same password as the source applicant (the hash is copied, nothing is printed)."""
import argparse
import sys
import time
from datetime import date

from sqlalchemy import delete, insert, select

from promoflow.db import session as db_session
from promoflow.db.base import Base
from promoflow.db.enums import CaseStatus, Gate, GateOutcome
from promoflow.db.models import AuditLogEntry, PromotionCase, ScopusEvidence, User, UserRole
from promoflow.db.models.org import AuthSession
from promoflow.dossier import section11
from promoflow.workflow import review_service

SOURCE_EMAIL = "samira.altamimi@promoflow.test"
HOD_EMAIL = "huda.salem@promoflow.test"
DEAN_EMAIL = "walid.mansour@promoflow.test"
DOMAIN = "@promoflow.test"
STAGES = {"hod": "demo.hod", "dean": "demo.dean", "chancellor": "demo.chancellor", "live": "demo.live"}
TARGET = {"hod": CaseStatus.HOD_REVIEW, "dean": CaseStatus.DEAN_REVIEW, "chancellor": CaseStatus.REFEREE_SELECTION}

# Tables that hold what the agents and the reviewers PRODUCE. They are never copied: the pipeline writes them again.
OUTPUTS = {
    "agent_run", "agent_assessment", "claim", "criterion_result", "item_result", "case_report", "case_status_history",
    "audit_log_entry", "dean_evaluation", "flag", "gate_decision", "rubric_score", "rubric_opinion","coauthored_paper_evaluation",
    "referee_candidate", "reviewer_assignment", "outreach_message", "referee_report", "referee_paper_grade",
}
SKIP_COLUMNS = {"id", "created_at", "updated_at", "uploaded_at"}


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _dossier_tables() -> list:
    """Every table that belongs to a case's dossier, in an order where parents come before their children."""
    chosen, names = [], {"promotion_case"}
    for t in Base.metadata.sorted_tables:
        if t.name in OUTPUTS or t.name == "promotion_case":
            continue
        if {fk.column.table.name for fk in t.foreign_keys} & names:
            chosen.append(t)
            names.add(t.name)
    return chosen


def _user_id(s, email: str) -> int:
    uid = s.scalar(select(User.id).where(User.email == email))
    if uid is None:
        raise SystemExit(f"No account {email}. Run the seed first.")
    return uid


def _case_of(s, user_id: int) -> PromotionCase | None:
    return s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == user_id)
                    .order_by(PromotionCase.id.desc()))


def _copy_user(s, source: User, email: str, employee_id: str) -> User:
    user = User(email=email, auth_provider=source.auth_provider, password_hash=source.password_hash,
                full_name=source.full_name, employee_id=employee_id, profile_completed_at=source.profile_completed_at,
                college_id=source.college_id, department_id=source.department_id)
    s.add(user)
    s.flush()
    for role in s.scalars(select(UserRole).where(UserRole.user_id == source.id)):     # the same roles as the source
        s.add(UserRole(user_id=user.id, role=role.role, department_id=role.department_id, college_id=role.college_id))
    return user


def _copy_case(s, source_case_id: int, user: User) -> PromotionCase:
    """Copy the case row and every dossier row, remapping the links between them to the new rows."""
    src = s.get(PromotionCase, source_case_id)
    cols = {c.name: getattr(src, c.name) for c in PromotionCase.__table__.columns if c.name not in SKIP_COLUMNS}
    cols.update(applicant_id=user.id, status=CaseStatus.DRAFT, submitted_at=None)
    new = PromotionCase(**cols)
    s.add(new)
    s.flush()

    ids: dict[str, dict[int, int]] = {"promotion_case": {src.id: new.id}}
    for table in _dossier_tables():
        ids[table.name] = {}
        if "case_id" in table.c:
            where = table.c.case_id == src.id
        else:                                            # a child of a child (e.g. a paper's authors)
            fk = next(fk for fk in table.foreign_keys if fk.column.table.name in ids)
            where = table.c[fk.parent.name].in_(list(ids[fk.column.table.name]))
        for row in s.execute(select(table).where(where)).mappings().all():
            values = {k: v for k, v in row.items() if k not in SKIP_COLUMNS}
            for fk in table.foreign_keys:
                col, target = fk.parent.name, fk.column.table.name
                if col == "uploaded_by":
                    values[col] = user.id
                elif col == "superseded_by_id":
                    values[col] = None
                elif target in ids and values.get(col) is not None:
                    values[col] = ids[target].get(values[col])
            if table.name == "case_document" and values.get("entity_table"):
                mapped = ids.get(values["entity_table"], {}).get(values["entity_id"])
                if mapped is None:
                    continue                             # its entry was not copied
                values["entity_id"] = mapped
            ids[table.name][row["id"]] = s.execute(insert(table).values(**values).returning(table.c.id)).scalar()

    evidence = s.scalar(select(ScopusEvidence).where(ScopusEvidence.case_id == new.id))
    if evidence is not None:
        evidence.screenshot_date = date.today()          # the rule wants a screenshot within 30 days of submission
    return new


def _get_or_make(s, key: str, source: User, source_case_id: int) -> tuple[User, PromotionCase]:
    email = f"{STAGES[key]}{DOMAIN}"
    user = s.scalar(select(User).where(User.email == email))
    if user is None:
        user = _copy_user(s, source, email, f"DEMO-{key.upper()}")
        _log(f"created account {email}")
    case = _case_of(s, user.id)
    if case is None:
        case = _copy_case(s, source_case_id, user)
        _log(f"copied dossier into case {case.id} for {email}")
    return user, case


def _status_of(case_id: int) -> CaseStatus:
    with db_session.session_scope() as s:
        return s.get(PromotionCase, case_id).status


def advance(case_id: int, applicant_id: int, target: CaseStatus) -> None:
    """Move one case forward, through the real services, until it waits at `target`. Safe to call again."""
    with db_session.session_scope() as s:
        hod, dean = _user_id(s, HOD_EMAIL), _user_id(s, DEAN_EMAIL)
    for _ in range(6):
        status = _status_of(case_id)
        if status == target:
            _log(f"case {case_id} is at {target.value}")
            return
        if status == CaseStatus.DRAFT:
            with db_session.session_scope() as s:
                section11.submit(s, applicant_id, date.today())
            _log(f"case {case_id} submitted")
        elif status == CaseStatus.SUBMITTED:
            _log(f"case {case_id}: agents running (about a minute or more on the free plan)...")
            review_service.start_review(case_id, wait=True)
        elif status == CaseStatus.HOD_REVIEW:
            _log(f"case {case_id}: Head approves")
            review_service.resume(case_id, hod, Gate.HOD, GateOutcome.APPROVE, "Approved for the demo.", wait=True)
        elif status == CaseStatus.DEAN_REVIEW:
            _log(f"case {case_id}: Dean approves (builds the referee shortlist)")
            review_service.resume(case_id, dean, Gate.DEAN, GateOutcome.APPROVE, "Approved for the demo.", wait=True)
        else:
            raise SystemExit(f"Case {case_id} ended at {status.value}; open its report to see why.")
        after = _status_of(case_id)
        if after == status:
            raise SystemExit(f"Case {case_id} did not move from {status.value}. Check the flags on its report.")
    raise SystemExit(f"Case {case_id} did not reach {target.value}.")


def cmd_stage(keys: list[str]) -> None:
    with db_session.session_scope() as s:
        source = s.scalar(select(User).where(User.email == SOURCE_EMAIL))
        src_case = _case_of(s, source.id)
        if src_case is None:
            raise SystemExit("The source applicant has no case to copy.")
        source_case_id = src_case.id
    for key in keys:
        _log(f"--- {key} ---")
        with db_session.session_scope() as s:
            source = s.scalar(select(User).where(User.email == SOURCE_EMAIL))
            user, case = _get_or_make(s, key, source, source_case_id)
            user_id, case_id = user.id, case.id
        if key != "live":
            advance(case_id, user_id, TARGET[key])
    cmd_status()


def cmd_status() -> None:
    with db_session.session_scope() as s:
        rows = s.execute(select(User.email, PromotionCase.id, PromotionCase.status)
                         .join(PromotionCase, PromotionCase.applicant_id == User.id)
                         .where(User.email.like(f"demo.%{DOMAIN}")).order_by(User.email)).all()
    _log("demo cases:")
    for email, case_id, status in rows:
        print(f"   {email:34} case {case_id:<4} {status.value}")
    if not rows:
        print("   (none)")


def cmd_reset(keys: list[str]) -> None:
    emails = [f"{STAGES[k]}{DOMAIN}" for k in keys]
    with db_session.session_scope() as s:
        users = s.scalars(select(User).where(User.email.in_(emails))).all()
        user_ids = [u.id for u in users]
        if not user_ids:
            _log("nothing to reset")
            return
        case_ids = list(s.scalars(select(PromotionCase.id).where(PromotionCase.applicant_id.in_(user_ids))))
        s.execute(delete(AuditLogEntry).where(AuditLogEntry.user_id.in_(user_ids)))
        if case_ids:
            s.execute(delete(AuditLogEntry).where(AuditLogEntry.case_id.in_(case_ids)))
            s.execute(delete(PromotionCase).where(PromotionCase.id.in_(case_ids)))   # children go with the case
        s.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        s.execute(delete(UserRole).where(UserRole.user_id.in_(user_ids)))
        s.execute(delete(User).where(User.id.in_(user_ids)))
        _log(f"removed {len(user_ids)} demo accounts and {len(case_ids)} cases")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m promoflow.demo_stage", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("stage", help="create and advance the demo cases")
    st.add_argument("which", nargs="*", choices=list(STAGES), help="default: all four")
    sub.add_parser("status", help="show the demo cases")
    rs = sub.add_parser("reset", help="delete demo accounts and their cases")
    rs.add_argument("which", nargs="*", choices=list(STAGES), help="default: all four")
    args = p.parse_args(argv)
    {"stage": lambda: cmd_stage(args.which or list(STAGES)), "status": cmd_status, "reset": lambda: cmd_reset(args.which or list(STAGES))}[args.cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
