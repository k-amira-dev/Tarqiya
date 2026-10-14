"""Section 7 – University & Community Service (spec chapter 11). Split into one module per Appendix F
evidence sub-section (7A-1..5, 7B); `load` bundles them for the UI in one call.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus
from promoflow.db.session import parallel
from promoflow.dossier.section0 import active_case
from promoflow.dossier.section7 import (
    admin_positions, committees, community, policy_contributions, trainings, workshops,
)


# Everything the Section 7 page needs: one list per kind of service entry.
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


# Read all of Section 7 for the page, with the independent readers running together.
def load(s: Session, user_id: int) -> Section7Context:
    case = active_case(s, user_id)
    if case is None:
        return Section7Context(None, None, [], [], [], [], [], [])
    cid = case.id
    results = parallel(
        lambda sess: committees.load(sess, cid), lambda sess: admin_positions.load(sess, cid),
        lambda sess: workshops.load(sess, cid), lambda sess: trainings.load(sess, cid),
        lambda sess: policy_contributions.load(sess, cid), lambda sess: community.load(sess, cid))
    return Section7Context(case.id, case.status, *results)
