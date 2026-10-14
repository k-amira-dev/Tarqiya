"""Research Agent (LLM + rules). Owner: Khadidja. STUB for now.
Replace the body of run(); keep the signature and return {"results": {"research": AgentOutput.model_dump(mode="json")}}.
You can test it alone: research.run({"case_id": 1}).

HOW TO REPLACE THIS STUB (step by step)
---------------------------------------
1. Keep the function name and signature: `def run(state: CaseState) -> dict`. The graph (graph.py) already calls it.
   `state["case_id"]` is the promotion case you are assessing.
2. Read what you need from the database with `db_session.session_scope()` (see nodes/teaching.py for a complete
   example). Send the language model record IDs and short facts, never names of people.
3. Build an `AgentOutput` (see schemas.py): a verdict, a narrative, criteria rows (required vs actual), flags for
   anything a person must look at, and claims that cite the records behind your statements.
4. Save it with `save_output(s, case_id, out)` from persist.py, and return
   `{"results": {"research": out.model_dump(mode="json")}}`. The Report Builder and the review pages then pick it up
   with no other change.
5. Keep the placeholder switch below (`use_stubs`) so the graph tests keep working without a database.

Useful things that already exist: promoflow/rules/research.py (journal Class A/B classification, ISBN check),
promoflow/workflow/verify.py (checks that every claim cites real records), and promoflow/workflow/rubric.py (the shared
scoring engine, if your agent scores against a rubric)."""
from promoflow.db.enums import Component
from promoflow.workflow.nodes import stub_result
from promoflow.workflow.schemas import CaseState


def run(state: CaseState) -> dict:
    # Placeholder: returns fake "pass" output so the whole graph runs end to end until the real agent is written.
    return stub_result(Component.RESEARCH)
