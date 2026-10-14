"""The stub graph: routing, parallel agents, human gates, pausing and resuming."""
import pytest
from langgraph.types import Command

from promoflow.workflow.graph import build_graph, memory_checkpointer
from promoflow.workflow.schemas import AgentOutput


# The stub switch keeps these tests about the graph's flow; the real checker has its own tests.
START = {"case_id": 1, "options": {"stub_eligible": True}}


@pytest.fixture
def graph():
    return build_graph(memory_checkpointer())


def cfg(name):
    return {"configurable": {"thread_id": name}}


def waiting_for(graph, config):
    tasks = graph.get_state(config).tasks
    return tasks[0].interrupts[0].value["gate"] if tasks and tasks[0].interrupts else None


def test_eligible_case_runs_three_agents_and_stops_at_hod(graph):
    c = cfg("a")
    graph.invoke(START, c)
    state = graph.get_state(c).values
    assert set(state["results"]) == {"eligibility", "research", "teaching", "service"}
    assert state["report"]["overall_pass"] is True
    assert waiting_for(graph, c) == "hod"


def test_agent_outputs_follow_the_shared_schema(graph):
    c = cfg("b")
    graph.invoke(START, c)
    for out in graph.get_state(c).values["results"].values():
        AgentOutput.model_validate(out)


def test_full_approval_path(graph):
    c = cfg("c")
    graph.invoke(START, c)
    graph.invoke(Command(resume={"outcome": "approve"}), c)
    assert waiting_for(graph, c) == "dean"
    graph.invoke(Command(resume={"outcome": "approve"}), c)
    assert waiting_for(graph, c) == "chancellor"
    graph.invoke(Command(resume={"selected": [2]}), c)
    state = graph.get_state(c).values
    assert state["selected_referees"] == [2]
    assert state["final_status"] == "referees_selected"


def test_not_eligible_ends_without_running_agents(graph):
    c = cfg("d")
    graph.invoke({"case_id": 1, "options": {"stub_eligible": False}}, c)
    state = graph.get_state(c).values
    assert state["final_status"] == "not_eligible"
    assert set(state["results"]) == {"eligibility"}


@pytest.mark.parametrize("gates, expected", [(0, "returned_by_hod"), (1, "returned_by_dean")])
def test_revision_ends_the_run(graph, gates, expected):
    c = cfg(f"e{gates}")
    graph.invoke(START, c)
    if gates:
        graph.invoke(Command(resume={"outcome": "approve"}), c)
    graph.invoke(Command(resume={"outcome": "return_for_revision", "sections": ["5"]}), c)
    assert graph.get_state(c).values["final_status"] == expected
