"""Section 6 – Teaching & Academic Advising (spec chapter 10). Split into one module per Appendix E
evidence sub-section (6A-6I); `load` bundles them for the UI in one call.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus
from promoflow.db.session import parallel
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
    cid = case.id
    results = parallel(
        lambda sess: courses.load(sess, cid), lambda sess: peer_observations.load(sess, cid),
        lambda sess: satisfaction.load(sess, cid), lambda sess: curriculum.load(sess, cid),
        lambda sess: advising.load(sess, cid), lambda sess: course_files.load(sess, cid),
        lambda sess: innovation.load(sess, cid), lambda sess: supervision.load(sess, cid),
        lambda sess: development.load(sess, cid), lambda sess: courses.registrar_report(sess, cid))
    return Section6Context(case.id, case.status, *results)
