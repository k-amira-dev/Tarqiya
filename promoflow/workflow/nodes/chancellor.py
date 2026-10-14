"""Chancellor's Office Agent: shortlist of up to 10 external referees with conflict-of-interest checks.
Owner: Khadidja. STUB for now. The Chancellor selects; the agent never approves."""
from promoflow.workflow.schemas import CaseState


def run(state: CaseState) -> dict:
    # Placeholder candidates (ids only). Real version: OpenAlex/Scopus search + COI checks -> referee_candidate rows.
    return {"shortlist": [{"candidate_id": i, "coi_clear": True} for i in range(1, 4)]}
