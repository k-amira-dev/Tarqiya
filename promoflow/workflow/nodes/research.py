"""Research Agent (LLM + rules). Owner: the Research/Chancellor teammate. STUB for now.
Replace the body of run(); keep the signature and return {"results": {"research": AgentOutput.model_dump(mode="json")}}.
You can test it alone: research.run({"case_id": 1})."""
from promoflow.db.enums import Component
from promoflow.workflow.nodes import stub_result
from promoflow.workflow.schemas import CaseState


def run(state: CaseState) -> dict:
    return stub_result(Component.RESEARCH)
