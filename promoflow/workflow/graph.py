"""The LangGraph workflow (matches System architecture.png):

    Eligibility -> [Research | Teaching | Service in parallel] -> Report Builder -> HoD gate -> Dean gate
                -> Chancellor's Office Agent -> Chancellor selects referees

Human gates use interrupt(): the run stops, the checkpointer saves it, and it continues when the reviewer's decision
arrives through Command(resume=...). "Not eligible" and "return for revision" end the run; a resubmitted case starts a
new run from the top. Statuses in the database are updated by promoflow/workflow/service.py (next step), not here."""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from promoflow.config import DATABASE_URL
from promoflow.workflow.nodes import chancellor, eligibility, report, research, service, teaching
from promoflow.workflow.schemas import CaseState

PARALLEL_AGENTS = ["research", "teaching", "service"]


def _finish(status: str):
    def node(state: CaseState) -> dict:
        return {"final_status": status}
    return node


def hod_gate(state: CaseState) -> dict:
    decision = interrupt({"gate": "hod", "case_id": state.get("case_id"), "report": state.get("report")})
    return {"hod": decision}


def dean_gate(state: CaseState) -> dict:
    decision = interrupt({"gate": "dean", "case_id": state.get("case_id"), "report": state.get("report"),
                          "hod": state.get("hod")})
    return {"dean": decision}


def referee_selection(state: CaseState) -> dict:
    """The Chancellor chooses from the shortlist. This is a selection, not an approval."""
    choice = interrupt({"gate": "chancellor", "case_id": state.get("case_id"), "shortlist": state.get("shortlist")})
    return {"selected_referees": choice.get("selected", []), "final_status": "referees_selected"}


def route_after_eligibility(state: CaseState):
    return PARALLEL_AGENTS if state.get("eligible") else "end_not_eligible"


def _approved(key: str):
    def route(state: CaseState) -> str:
        return "approve" if state.get(key, {}).get("outcome") == "approve" else "revise"
    return route


def build_graph(checkpointer=None):
    g = StateGraph(CaseState)
    g.add_node("eligibility", eligibility.run)
    g.add_node("research", research.run)
    g.add_node("teaching", teaching.run)
    g.add_node("service", service.run)
    g.add_node("report", report.run)
    g.add_node("hod_gate", hod_gate)
    g.add_node("dean_gate", dean_gate)
    g.add_node("chancellor", chancellor.run)
    g.add_node("referee_selection", referee_selection)
    g.add_node("end_not_eligible", _finish("not_eligible"))
    g.add_node("end_hod_revision", _finish("returned_by_hod"))
    g.add_node("end_dean_revision", _finish("returned_by_dean"))

    g.add_edge(START, "eligibility")
    g.add_conditional_edges("eligibility", route_after_eligibility, PARALLEL_AGENTS + ["end_not_eligible"])
    g.add_edge(PARALLEL_AGENTS, "report")            # waits until all three have finished
    g.add_edge("report", "hod_gate")
    g.add_conditional_edges("hod_gate", _approved("hod"), {"approve": "dean_gate", "revise": "end_hod_revision"})
    g.add_conditional_edges("dean_gate", _approved("dean"), {"approve": "chancellor", "revise": "end_dean_revision"})
    g.add_edge("chancellor", "referee_selection")
    g.add_edge("referee_selection", END)
    for name in ("end_not_eligible", "end_hod_revision", "end_dean_revision"):
        g.add_edge(name, END)
    return g.compile(checkpointer=checkpointer)


# ---- where paused runs are saved -------------------------------------------------------------------------------
# Postgres (Supabase) in the real system, so a case waiting for the HoD survives restarts; in memory for tests/demos.

def memory_checkpointer() -> MemorySaver:
    return MemorySaver()


def postgres_checkpointer():
    """Creates a small connection pool and a PostgresSaver on it. Call `.setup()` once
    (`python -m promoflow.workflow.tools setup-db`)."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    conninfo = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)   # psycopg wants the plain scheme
    pool = ConnectionPool(
        conninfo, min_size=1, max_size=3, open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},   # required by PostgresSaver
    )
    return PostgresSaver(pool)
