"""Service Agent (Appendix F rubric, 10 points, pass mark from the SERVICE_PASS_POINTS setting). Owner: Amira. STUB."""
from promoflow.db.enums import Component
from promoflow.workflow.nodes import stub_result
from promoflow.workflow.schemas import CaseState


def run(state: CaseState) -> dict:
    return stub_result(Component.SERVICE)
