"""One module per component. Owners: eligibility / teaching / service / report -> Amira;
research / chancellor -> Khadidja. Each module exposes one function `run(state)`
that returns a partial state update. Replace the body of `run` when the real agent is ready; keep the signature.

This file also holds the placeholder ("stub") helpers used by agents that are not written yet, and by tests and
demos that exercise the graph's flow without a dossier or a language model."""
from promoflow.db.enums import Component, Confidence, FlagSeverity, Verdict
from promoflow.workflow.schemas import AgentOutput, CriterionOut, FlagOut


def use_stubs(state: dict) -> bool:
    """True when a test or demo asked for placeholder agents (options: {"stubs": True}, or the older
    {"stub_eligible": ...} switch)."""
    options = state.get("options", {})
    return bool(options.get("stubs")) or "stub_eligible" in options


def stub_result(component: Component, verdict: Verdict = Verdict.PASS) -> dict:
    out = AgentOutput(
        component=component,
        verdict=verdict,
        narrative=f"STUB: the {component.value} agent is not written yet; this is placeholder output.",
        criteria=[CriterionOut(key=f"{component.value}_placeholder", label="Placeholder criterion",
                               required=1, actual=1, passed=verdict == Verdict.PASS)],
        flags=[FlagOut(severity=FlagSeverity.INFO, code="stub_output",
                       message=f"{component.value} returned placeholder output.")],
        confidence=Confidence.LOW,
        is_stub=True,
    )
    return {"results": {component.value: out.model_dump(mode="json")}}
