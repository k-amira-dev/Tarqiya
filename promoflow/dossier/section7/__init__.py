"""Section 7 – University & Community Service (spec chapter 11). Split into one module per Appendix F
evidence sub-section (7A-1..5, 7B); `load` bundles them for the UI in one call.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus
from promoflow.dossier.section0 import active_case
from promoflow.dossier.section7 import (
    admin_positions, committees, community, policy_contributions, trainings, workshops,
)


@dataclass(frozen=True)
class Section7Context:
    case_id: int | None
    status: CaseStatus | None
    committees: list["committees.CommitteeRow"]
    admin_positions: list["admin_positions.AdminPositionRow"]
    workshops: list["workshops.WorkshopRow"]
    trainings: list["trainings.TrainingRow"]
    policy_contributions: list["policy_contributions.PolicyContributionRow"]
    community: list["community.CommunityActivityRow"]


def load(s: Session, user_id: int) -> Section7Context:
    case = active_case(s, user_id)
    if case is None:
        return Section7Context(None, None, [], [], [], [], [], [])
    return Section7Context(
        case.id, case.status, committees.load(s, case.id), admin_positions.load(s, case.id),
        workshops.load(s, case.id), trainings.load(s, case.id), policy_contributions.load(s, case.id),
        community.load(s, case.id),
    )
