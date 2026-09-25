"""Account management from the command line (until the Admin › Users & roles page exists).

    python -m promoflow.admin create-user --email name@sharjah.ac.ae --name "Dr. Full Name" \
        --college "College of Arts, Humanities and Social Sciences" --department "Sociology"
    python -m promoflow.admin set-password --email name@sharjah.ac.ae

The password is typed at a hidden prompt: it is never passed on the command line or stored in any file.
Colleges and departments that do not exist yet are created.
"""
import argparse
import getpass
import re
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from promoflow.auth.passwords import hash_password
from promoflow.db.enums import AuthProvider, RoleName
from promoflow.db.models import AuditLogEntry, College, Department, User, UserRole
from promoflow.db.session import session_scope

MIN_PASSWORD = 10
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdminError(Exception):
    pass


def _code(name: str, taken: set[str]) -> str:
    """Short unique code from the initials, e.g. 'College of Arts, Humanities and Social Sciences' -> 'CAHSS'."""
    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in {"of", "and", "the", "for"}]
    base = ("".join(w[0] for w in words) if len(words) > 1 else name[:6]).upper() or "X"
    code, n = base, 2
    while code in taken:
        code, n = f"{base}{n}", n + 1
    return code


def get_or_create_college(s: Session, name: str) -> College:
    college = s.scalar(select(College).where(func.lower(College.name_en) == name.strip().lower()))
    if college is None:
        college = College(code=_code(name, set(s.scalars(select(College.code)))), name_en=name.strip())
        s.add(college)
        s.flush()
    return college


def get_or_create_department(s: Session, college: College, name: str) -> Department:
    dept = s.scalar(select(Department).where(Department.college_id == college.id,
                                             func.lower(Department.name_en) == name.strip().lower()))
    if dept is None:
        dept = Department(code=_code(name, set(s.scalars(select(Department.code)))), name_en=name.strip(),
                          college_id=college.id)
        s.add(dept)
        s.flush()
    return dept


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AdminError(f"The password must be at least {MIN_PASSWORD} characters.")


def create_user(s: Session, *, email: str, full_name: str, college: str, department: str, password: str,
                roles: list[RoleName]) -> User:
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise AdminError(f"'{email}' is not a valid email address.")
    if s.scalar(select(User).where(User.email == email)) is not None:
        raise AdminError(f"An account with {email} already exists. Use set-password to change its password.")
    check_password(password)
    c = get_or_create_college(s, college)
    d = get_or_create_department(s, c, department)
    user = User(email=email, auth_provider=AuthProvider.LOCAL, password_hash=hash_password(password),
                full_name=full_name.strip(), college_id=c.id, department_id=d.id)
    s.add(user)
    s.flush()
    for role in roles:
        scope = {"department_id": d.id} if role == RoleName.HOD else {"college_id": c.id} if role == RoleName.DEAN else {}
        s.add(UserRole(user_id=user.id, role=role, **scope))
    s.add(AuditLogEntry(action="user_created", entity_table="app_user", entity_id=user.id,
                        after={"email": email, "roles": [r.value for r in roles], "college": c.name_en,
                               "department": d.name_en}))
    return user


def set_password(s: Session, email: str, password: str) -> None:
    user = s.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise AdminError(f"No account with {email}.")
    check_password(password)
    user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    s.add(AuditLogEntry(action="password_set", entity_table="app_user", entity_id=user.id))


def _ask_password() -> str:
    first = getpass.getpass(f"New password (at least {MIN_PASSWORD} characters, hidden while typing): ")
    if first != getpass.getpass("Type it again: "):
        raise AdminError("The two passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m promoflow.admin", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cu = sub.add_parser("create-user", help="create an account")
    cu.add_argument("--email", required=True)
    cu.add_argument("--name", required=True, help='full name, e.g. "Dr. Full Name"')
    cu.add_argument("--college", required=True)
    cu.add_argument("--department", required=True)
    cu.add_argument("--role", action="append", choices=[r.value for r in RoleName],
                    help="repeat for several roles (default: applicant)")
    sp = sub.add_parser("set-password", help="set a new password for an existing account")
    sp.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    try:
        password = _ask_password()
        with session_scope() as s:
            if args.command == "create-user":
                roles = [RoleName(r) for r in (args.role or ["applicant"])]
                user = create_user(s, email=args.email, full_name=args.name, college=args.college,
                                   department=args.department, password=password, roles=roles)
                print(f"Created {user.email} ({', '.join(r.value for r in roles)}) in "
                      f"{args.department}, {args.college}.")
                print("At first login they confirm their name and enter their employee ID.")
            else:
                set_password(s, args.email, password)
                print(f"Password updated for {args.email.strip().lower()}.")
    except AdminError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
