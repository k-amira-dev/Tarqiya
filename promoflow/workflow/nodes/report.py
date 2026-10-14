"""Report Builder (plain function, no LLM). Owner: Amira.
Already real in a minimal form: it merges the agents' outputs, lists every flag and recomputes the overall result
from the verdicts. The fixed report template and saving to case_report come later."""
from promoflow.db.enums import Verdict
from promoflow.workflow.schemas import CaseState

AGENTS = ("research", "teaching", "service")


def build_report(results: dict) -> dict:
    present = {name: results[name] for name in AGENTS if name in results}
    eligibility = results.get("eligibility")           # shown to the reviewers; its flags (e.g. an exceptional-case
    shown = {**({"eligibility": eligibility} if eligibility else {}), **present}   # request) must reach the HoD
    flags = [dict(flag, component=name) for name, out in shown.items() for flag in out.get("flags", [])]
    verdicts = {name: out["verdict"] for name, out in present.items()}
    missing = [name for name in AGENTS if name not in present]
    # Recomputed here, never copied from an agent: all three must pass, any gap needs a human.
    needs_human = [Verdict.NEEDS_HUMAN.value, Verdict.INCOMPLETE.value]
    if missing or any(v in needs_human for v in verdicts.values()) or (
            eligibility and eligibility["verdict"] == Verdict.NEEDS_HUMAN.value):
        overall = None
    else:
        overall = all(v == Verdict.PASS.value for v in verdicts.values())
    return {"overall_pass": overall, "verdicts": verdicts, "missing": missing, "flags": flags,
            "eligibility": eligibility, "sections": present}


def run(state: CaseState) -> dict:
    return {"report": build_report(state.get("results", {}))}
