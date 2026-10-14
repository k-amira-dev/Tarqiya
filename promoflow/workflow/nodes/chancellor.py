"""Chancellor's Office Agent: shortlist of up to 10 external referees with conflict-of-interest checks.
Owner: Khadidja. STUB for now. The Chancellor selects; the agent never approves.

HOW IT FITS IN: this node runs AFTER the Dean has approved the case. It prepares a shortlist of candidate referees
and stores it in `state["shortlist"]`. The graph then pauses (graph.py, `referee_selection`) and shows the shortlist
to the Chancellor, who picks the referees. Nothing here decides anything: it only prepares the choice.

TO DO (real version): search for candidates (OpenAlex / Scopus), remove conflicts of interest (co-authorship, same
institution, a referee used in the last 5 years), keep at most 10, and save them as `referee_candidate` rows. Send the
language model ids and facts only, never names. The output stays `{"shortlist": [...]}` so the graph and the
Chancellor's page need no change."""
from promoflow.workflow.schemas import CaseState


def run(state: CaseState) -> dict:
    # Placeholder candidates (ids only). Real version: OpenAlex/Scopus search + COI checks -> referee_candidate rows.
    return {"shortlist": [{"candidate_id": i, "coi_clear": True} for i in range(1, 4)]}
