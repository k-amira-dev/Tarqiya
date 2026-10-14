"""The LangGraph workflow (matches System architecture.png):

    Eligibility -> [Research | Teaching | Service in parallel] -> Report Builder -> HoD gate -> Dean gate
                -> Chancellor's Office Agent -> Chancellor selects referees

Human gates use interrupt(): the run stops, the checkpointer saves it, and it continues when the reviewer's decision
arrives through Command(resume=...). "Not eligible" and "return for revision" end the run; a resubmitted case starts a
new run from the top. Statuses in the database are updated by promoflow/workflow/review_service.py, not here.

NEW TO LANGGRAPH? Read this first
---------------------------------
A LangGraph "graph" is a flowchart written in code:
  * a NODE is a Python function. It receives the current state (a dictionary, see CaseState in schemas.py) and
    returns ONLY the keys it wants to change. LangGraph merges that into the state for the next node.
  * an EDGE says which node runs after which. A *conditional* edge runs a small function that looks at the state
    and decides where to go next (for example "eligible? go to the agents, otherwise stop").
  * a CHECKPOINTER saves the state after every step, so a run can pause (waiting for a human) and be continued
    hours or days later, even after the program restarted.
Everything below is just wiring: it builds that flowchart. The real work happens inside the node functions, which
live in promoflow/workflow/nodes/ (one file per agent)."""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from promoflow.config import DATABASE_URL
from promoflow.workflow.nodes import chancellor, eligibility, report, research, service, teaching
from promoflow.workflow.schemas import CaseState

# The three agents that run at the same time once a case is found eligible. Their names must match the node names
# registered in build_graph() below.
PARALLEL_AGENTS = ["research", "teaching", "service"]


def _finish(status: str):
    """Build a tiny node that just records HOW the run ended ("not_eligible", "returned_by_hod", ...).

    We need three nearly identical nodes, so this function makes them (a "factory"). review_service.py later reads
    `final_status` to decide which case status to store in the database."""
    def node(state: CaseState) -> dict:
        return {"final_status": status}
    return node


def hod_gate(state: CaseState) -> dict:
    """The Head of Department's approval gate.

    interrupt() PAUSES the whole run right here and hands the given dictionary to whoever started it (the review
    page uses it to show the report). When the HoD later clicks a button, review_service.resume() restarts the graph
    with the decision, and interrupt() returns that decision. We store it under the key "hod"."""
    decision = interrupt({"gate": "hod", "case_id": state.get("case_id"), "report": state.get("report")})
    return {"hod": decision}


def dean_gate(state: CaseState) -> dict:
    """Same idea as hod_gate, for the Dean. The Dean also gets to see what the HoD decided."""
    decision = interrupt({"gate": "dean", "case_id": state.get("case_id"), "report": state.get("report"),
                          "hod": state.get("hod")})
    return {"dean": decision}


def referee_selection(state: CaseState) -> dict:
    """The Chancellor chooses from the shortlist. This is a selection, not an approval."""
    choice = interrupt({"gate": "chancellor", "case_id": state.get("case_id"), "shortlist": state.get("shortlist")})
    return {"selected_referees": choice.get("selected", []), "final_status": "referees_selected"}


def route_after_eligibility(state: CaseState):
    """Decide what runs after the Eligibility Checker.

    Returning a LIST of node names makes LangGraph start all of them in parallel. Returning one name sends the run
    to that single node (here: the "not eligible" ending)."""
    return PARALLEL_AGENTS if state.get("eligible") else "end_not_eligible"


def _approved(key: str):
    """Build a routing function for a gate: "approve" if the reviewer approved, otherwise "revise".

    `key` is where the decision was stored in the state ("hod" or "dean")."""
    def route(state: CaseState) -> str:
        return "approve" if state.get(key, {}).get("outcome") == "approve" else "revise"
    return route


def build_graph(checkpointer=None):
    """Assemble and compile the whole flowchart.

    `checkpointer` is where paused runs are saved: Postgres in the real app, memory in tests. Without one the graph
    still runs, but it cannot pause and resume (interrupt() needs a checkpointer)."""
    g = StateGraph(CaseState)

    # 1) Register every node (a name plus the function that runs). `.run` is the function each agent file exposes.
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

    # 2) Connect them. START is LangGraph's built-in "begin here" marker, END is "stop here".
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

    # 3) Compile = check the wiring and produce a runnable object (graph.invoke(...), graph.stream(...)).
    return g.compile(checkpointer=checkpointer)


# ---- where paused runs are saved -------------------------------------------------------------------------------
# Postgres (Supabase) in the real system, so a case waiting for the HoD survives restarts; in memory for tests/demos.

def memory_checkpointer() -> MemorySaver:
    """Keeps paused runs in RAM only. Fast and needs no database, but everything is lost when the program stops."""
    return MemorySaver()


def postgres_checkpointer():
    """Creates a small connection pool and a PostgresSaver on it. Call `.setup()` once
    (`python -m promoflow.workflow.tools setup-db`)."""
    # Imported here (not at the top) so tests that only use memory_checkpointer() never need these libraries loaded.
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    conninfo = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)   # psycopg wants the plain scheme
    # A "pool" keeps a few database connections open and reuses them (opening a new one is slow when the database
    # is far away). max_size=3 is deliberately small: Supabase limits how many connections one project may open.
    pool = ConnectionPool(
        conninfo, min_size=1, max_size=3, open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},   # required by PostgresSaver
    )
    return PostgresSaver(pool)
