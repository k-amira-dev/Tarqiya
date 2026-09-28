"""Section 6 – Teaching & Academic Advising (spec chapter 10). Split into one module per Appendix E
evidence sub-section (6A-6I); `load` bundles them for the UI in one call.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus
from promoflow.dossier.section0 import active_case
from promoflow.dossier.section6 import (
    advising, course_files, courses, curriculum, development, innovation, peer_observations, satisfaction,
    supervision,
)


@dataclass(frozen=True)
class Section6Context:
    case_id: int | None
    status: CaseStatus | None
    courses: list
    peer_observations: list["peer_observations.PeerObservationRow"]
    satisfaction: list["satisfaction.SatisfactionRow"]
    curriculum: list["curriculum.CurriculumRow"]
    advising: list["advising.AdvisingRow"]
    course_files: list["course_files.CourseFileRow"]
    innovation: list["innovation.InnovationRow"]
    supervision: list["supervision.SupervisionRow"]
    development: list["development.DevelopmentRow"]
    registrar_report: object


def load(s: Session, user_id: int) -> Section6Context:
    case = active_case(s, user_id)
    if case is None:
        return Section6Context(None, None, [], [], [], [], [], [], [], [], [], None)
    return Section6Context(
        case.id, case.status, courses.load(s, case.id), peer_observations.load(s, case.id),
        satisfaction.load(s, case.id), curriculum.load(s, case.id), advising.load(s, case.id),
        course_files.load(s, case.id), innovation.load(s, case.id), supervision.load(s, case.id),
        development.load(s, case.id), courses.registrar_report(s, case.id),
    )
