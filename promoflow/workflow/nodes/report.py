"""Report Builder (plain function, no LLM). Owner: Amira.

It merges the agents' outputs into one report: every agent's verdict, every flag, and the overall result, which it
RECOMPUTES itself from the verdicts instead of trusting any agent. review_service.py saves the report to the
`case_report` table. A fixed printable template for the report comes later.

HOW IT FITS IN: the graph runs Research, Teaching and Service in parallel; each one adds its result to
`state["results"]`. This node runs after all three have finished, reads that dictionary and produces `state["report"]`,
which is what the Head of Department and the Dean see."""
from promoflow.db.enums import Verdict
from promoflow.workflow.schemas import CaseState

# The agents whose verdicts decide the overall result. (Eligibility is shown in the report but was already decided
# before these three ran.)
AGENTS = ("research", "teaching", "service")


def build_report(results: dict) -> dict:
    """Turn the agents' result dictionaries into one report dictionary. A plain function, so it is easy to test."""
    present = {name: results[name] for name in AGENTS if name in results}
    eligibility = results.get("eligibility")           # shown to the reviewers; its flags (e.g. an exceptional-case
    shown = {**({"eligibility": eligibility} if eligibility else {}), **present}   # request) must reach the HoD
    # One list with every flag from every agent, each tagged with the agent it came from.
    flags = [dict(flag, component=name) for name, out in shown.items() for flag in out.get("flags", [])]
    verdicts = {name: out["verdict"] for name, out in present.items()}
    missing = [name for name in AGENTS if name not in present]
    # Recomputed here, never copied from an agent: all three must pass, any gap needs a human.
    needs_human = [Verdict.NEEDS_HUMAN.value, Verdict.INCOMPLETE.value]
    if missing or any(v in needs_human for v in verdicts.values()) or (
            eligibility and eligibility["verdict"] == Verdict.NEEDS_HUMAN.value):
        overall = None          # None = "a person must decide", not pass and not fail
    else:
        overall = all(v == Verdict.PASS.value for v in verdicts.values())
    return {"overall_pass": overall, "verdicts": verdicts, "missing": missing, "flags": flags,
            "eligibility": eligibility, "sections": present}


def run(state: CaseState) -> dict:
    """The graph calls this. It returns only the key it fills in: `report`."""
    return {"report": build_report(state.get("results", {}))}
