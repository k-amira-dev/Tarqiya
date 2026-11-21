"""Submit one of the 20 generated dossiers through the app's own services and record everything the agents produced.

    python -m promoflow.batch_submit A01            submit the draft, run the agents, stop where the case waits (the Head's gate)
    python -m promoflow.batch_submit status         one line per batch case
    python -m promoflow.batch_submit collect A01    (re)write the result file of a case that already ran, without calling the model

What it does is exactly what the Submit button and the review page do: section11.submit, then review_service.start_review. Nothing is scored
by this script. The submission window is skipped (DEV_IGNORE_SUBMISSION_WINDOW) because the batch is run outside the first week of
January, April or October; the rules are still evaluated by the app.

Result of one run: docs/generated_dossiers/_results/<code>.json. It holds the time, the tokens the model calls used, the status the case reached,
the verdict and narrative of every agent, the criteria table, the item results, every rubric score with its rationale and the model that gave
it, the flags, and the report."""
import json
import os
import sys
import threading
import time
from datetime import date
from pathlib import Path

os.environ.setdefault("DEV_IGNORE_SUBMISSION_WINDOW", "1")       # must be set before promoflow.config is imported

from promoflow.batch_read import ROOT                                    # noqa: E402

RESULTS = ROOT / "_results"


# ---- token counting ---------------------------------------------------------------------------------------------------

class Tally:
    """Adds up what every model call of one run used. LangChain reports usage on each response; a failed call (rate limit) is counted too."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls = self.errors = self.input = self.output = 0
        self.by_model: dict[str, dict] = {}

    def add(self, model: str, i: int, o: int):
        with self.lock:
            self.calls += 1
            self.input += i
            self.output += o
            m = self.by_model.setdefault(model, {"calls": 0, "input": 0, "output": 0})
            m["calls"] += 1
            m["input"] += i
            m["output"] += o

    def as_dict(self):
        return {"calls": self.calls, "failed_calls": self.errors, "input_tokens": self.input, "output_tokens": self.output,
                "total_tokens": self.input + self.output, "by_model": self.by_model}


def patch_counter(tally: "Tally") -> None:
    """Count every chat-model call in the process, whichever thread makes it (the committee scores in worker threads, which a context-based
    hook does not reach). A call that raises (rate limit) is counted as failed."""
    from langchain_core.language_models.chat_models import BaseChatModel

    if getattr(BaseChatModel, "_batch_counted", False):
        BaseChatModel._batch_tally = tally
        return
    original = BaseChatModel._generate_with_cache

    def counted(self, *a, **k):
        t = getattr(BaseChatModel, "_batch_tally", None)
        try:
            result = original(self, *a, **k)
        except Exception:
            if t:
                with t.lock:
                    t.errors += 1
            raise
        if t:
            for g in result.generations:
                msg = getattr(g, "message", None)
                um = getattr(msg, "usage_metadata", None) or {}
                meta = getattr(msg, "response_metadata", None) or {}
                tu = meta.get("token_usage") or {}
                t.add(str(meta.get("model_name") or meta.get("model") or getattr(self, "model_name", None) or getattr(self, "model", None) or "?"),
                      int(um.get("input_tokens") or tu.get("prompt_tokens") or 0), int(um.get("output_tokens") or tu.get("completion_tokens") or 0))
        return result

    BaseChatModel._generate_with_cache = counted
    BaseChatModel._batch_counted = True
    BaseChatModel._batch_tally = tally


def install_counter(tally: Tally) -> None:
    patch_counter(tally)


# ---- finding the case -------------------------------------------------------------------------------------------------

def _case_of(code: str):
    from sqlalchemy import select

    from promoflow.db import session as db
    from promoflow.db.models import PromotionCase, User

    x = json.loads((ROOT / "_expected" / f"{code}.json").read_text(encoding="utf-8"))
    with db.session_scope() as s:
        u = s.scalar(select(User).where(User.email == x["A"]["email"]))
        if u is None:
            raise SystemExit(f"{code}: no account for {x['A']['email']}; run  python -m promoflow.batch_load users")
        c = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == u.id).order_by(PromotionCase.id.desc()))
        if c is None:
            raise SystemExit(f"{code}: no case; run  python -m promoflow.batch_load load {code}")
        return x, u.id, c.id, c.status


# ---- collecting what the agents produced ------------------------------------------------------------------------------

def collect(code: str) -> dict:
    from sqlalchemy import select

    from promoflow.db import session as db
    from promoflow.db.models import (
        AgentAssessment, AgentRun, CaseReport, CaseStatusHistory, CriterionResult, Flag, ItemResult, RubricOpinion, RubricScore,
    )
    from promoflow.db.models.reference import RubricItem

    x, uid, case_id, _ = _case_of(code)
    enum = lambda v: getattr(v, "value", v)                              # noqa: E731
    num = lambda v: None if v is None else float(v)                      # noqa: E731
    out = {"code": code, "case_id": case_id, "applicant": x["A"]["name"], "track": x["A"]["track"], "applying_for": x["A"]["rank_applied"]}
    with db.session_scope() as s:
        from promoflow.db.models import PromotionCase
        case = s.get(PromotionCase, case_id)
        out["status"] = enum(case.status)
        out["history"] = [{"to": enum(h.to_status), "at": h.changed_at.isoformat() if h.changed_at else None, "note": h.note}
                          for h in s.scalars(select(CaseStatusHistory).where(CaseStatusHistory.case_id == case_id).order_by(CaseStatusHistory.id))]
        runs = list(s.scalars(select(AgentRun).where(AgentRun.case_id == case_id).order_by(AgentRun.id)))
        out["runs"] = [{"component": enum(r.component), "status": enum(r.status), "model": r.model_name, "prompt_version": r.prompt_version,
                        "seconds": (round((r.finished_at - r.started_at).total_seconds(), 1) if r.finished_at and r.started_at else None),
                        "error": r.error} for r in runs]
        out["assessments"] = []
        for a in s.scalars(select(AgentAssessment).where(AgentAssessment.case_id == case_id).order_by(AgentAssessment.id)):
            out["assessments"].append({
                "component": enum(a.component), "verdict": enum(a.verdict), "narrative": a.narrative,
                "criteria": [{"key": c.criterion_key, "label": c.label, "required": num(c.required_value), "actual": num(c.actual_value),
                              "passed": c.passed, "policy": c.policy_ref}
                             for c in s.scalars(select(CriterionResult).where(CriterionResult.assessment_id == a.id).order_by(CriterionResult.id))],
                "items": [{"table": i.entity_table, "id": i.entity_id, "counted": i.counted, "classification": i.classification,
                           "credited_role": i.credited_role, "basis": enum(i.basis), "confidence": enum(i.confidence), "reason": i.reason}
                          for i in s.scalars(select(ItemResult).where(ItemResult.assessment_id == a.id).order_by(ItemResult.id))]})
        scores = []
        for sc, it in s.execute(select(RubricScore, RubricItem).join(RubricItem, RubricItem.id == RubricScore.rubric_item_id)
                                .where(RubricScore.case_id == case_id).order_by(RubricItem.rubric_id, RubricItem.item_no)):
            ops = [{"model": o.model_name, "points": num(o.points), "confidence": o.confidence, "rationale": o.rationale}
                   for o in s.scalars(select(RubricOpinion).where(RubricOpinion.rubric_score_id == sc.id).order_by(RubricOpinion.id))]
            scores.append({"rubric_id": it.rubric_id, "item_no": it.item_no, "text": it.text_en, "min": num(it.min_points),
                           "max": num(it.max_points), "points": num(sc.suggested_points), "basis": enum(sc.suggestion_basis),
                           "confidence": enum(sc.confidence), "rationale": sc.suggestion_rationale, "opinions": ops})
        out["rubric_scores"] = scores
        out["flags"] = [{"severity": enum(f.severity), "code": f.code, "message": f.message}
                        for f in s.scalars(select(Flag).where(Flag.case_id == case_id).order_by(Flag.id))]
        rep = s.scalar(select(CaseReport).where(CaseReport.case_id == case_id).order_by(CaseReport.version.desc()))
        out["overall_pass"] = rep.overall_pass if rep else None
        out["report"] = rep.content if rep else None
    return out


def _save(code: str, data: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / f"{code}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return p


# ---- running ----------------------------------------------------------------------------------------------------------

def submit(code: str, log=print) -> dict:
    from promoflow.db import session as db
    from promoflow.db.enums import CaseStatus
    from promoflow.dossier import section11
    from promoflow.workflow import review_service

    x, uid, case_id, status = _case_of(code)
    prior = RESULTS / f"{code}.json"
    if status != CaseStatus.DRAFT:
        raise SystemExit(f"{code}: case {case_id} is {status.value}, not a draft; nothing submitted. "
                         f"(result file: {'present' if prior.exists() else 'absent'}; `collect {code}` rewrites it from the database)")
    tally = Tally()
    install_counter(tally)
    t0 = time.time()
    with db.session_scope() as s:
        section11.submit(s, uid, date.today())
    log(f"{code}: submitted case {case_id}; the agents are running...")
    review_service.start_review(case_id, wait=True)
    secs = round(time.time() - t0, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{code}_run.json").write_text(json.dumps({"seconds": secs, "tokens": tally.as_dict(), "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                          "error": review_service.get_status(case_id).error}), encoding="utf-8")     # kept first: tokens cannot be recovered later
    data = collect(code)
    data["run"] = {"seconds": secs, "tokens": tally.as_dict(), "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "error": review_service.get_status(case_id).error}
    p = _save(code, data)
    log(f"{code}: finished in {secs}s, case is now '{data['status']}', {tally.input + tally.output} tokens in {tally.calls} calls -> {p}")
    return data


def rerun_teaching(code: str, log=print, reason: str = "teaching scored again", component: str = "teaching", rubric_id: int = 1) -> dict:
    """Score the Teaching agent again on a case that was already reviewed (after a record was corrected). The earlier answer is kept in the
    result file next to the new one; the app's own save replaces the rubric lines and keeps the old model_score audit rows."""
    import importlib

    agent = importlib.import_module(f"promoflow.workflow.nodes.{component}")

    x, uid, case_id, status_now = _case_of(code)
    before = collect(code)
    tally = Tally()
    patch_counter(tally)
    t0 = time.time()
    agent.run({"case_id": case_id})
    secs = round(time.time() - t0, 1)
    after = collect(code)
    note = {"component": component, "reason": reason, "seconds": secs,
            "tokens": tally.as_dict(), "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "before": [s_ for s_ in before["rubric_scores"] if s_["rubric_id"] == rubric_id], "after": [s_ for s_ in after["rubric_scores"] if s_["rubric_id"] == rubric_id]}
    (RESULTS / f"{code}_rerun_{component}.json").write_text(json.dumps(note, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    run = RESULTS / f"{code}_run.json"
    after["run"] = json.loads(run.read_text(encoding="utf-8")) if run.exists() else None
    after["reruns"] = (json.loads((RESULTS / f"{code}.json").read_text(encoding="utf-8")).get("reruns") or []) + [note]
    _save(code, after)
    log(f"{code}: teaching scored again in {secs}s, {tally.input + tally.output} tokens in {tally.calls} calls")
    return note


def rerun_research(code: str, log=print) -> dict:
    """Run the Research agent again on a reviewed case (its model call was refused by a per-minute limit). Rule results do not change."""
    from promoflow.workflow.nodes import research

    x, uid, case_id, _ = _case_of(code)
    before = collect(code)
    tally = Tally()
    patch_counter(tally)
    t0 = time.time()
    research.run({"case_id": case_id})
    secs = round(time.time() - t0, 1)
    after = collect(code)
    pick = lambda d: [{"verdict": a["verdict"], "narrative": a["narrative"]} for a in d["assessments"] if a["component"] == "research"][-1]    # noqa: E731
    note = {"component": "research", "reason": "model call refused by a per-minute limit; run again", "seconds": secs, "tokens": tally.as_dict(),
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"), "before": pick(before), "after": pick(after),
            "flags_before": [f["code"] for f in before["flags"]], "flags_after": [f["code"] for f in after["flags"]]}
    (RESULTS / f"{code}_rerun_research.json").write_text(json.dumps(note, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    run = RESULTS / f"{code}_run.json"
    after["run"] = json.loads(run.read_text(encoding="utf-8")) if run.exists() else None
    after["reruns"] = (json.loads((RESULTS / f"{code}.json").read_text(encoding="utf-8")).get("reruns") or []) + [note]
    _save(code, after)
    log(f"{code}: research ran again in {secs}s, {tally.input + tally.output} tokens in {tally.calls} calls")
    return note


def status() -> int:
    from sqlalchemy import select

    from promoflow.batch_read import dossier_folder
    from promoflow.db import session as db
    from promoflow.db.models import PromotionCase, User

    codes = sorted(p.name.split("_")[0] for p in ROOT.glob("[AP][0-9][0-9]_*"))
    with db.session_scope() as s:
        for code in codes:
            x = json.loads((ROOT / "_expected" / f"{code}.json").read_text(encoding="utf-8"))
            u = s.scalar(select(User).where(User.email == x["A"]["email"]))
            c = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == u.id)) if u else None
            done = "result saved" if (RESULTS / f"{code}.json").exists() else "-"
            print(f"{code:4} {x['A']['name'][:28]:28} {x['A']['rank_applied'][:22]:22} case {c.id if c else '-':>3}  "
                  f"{getattr(c.status, 'value', '-') if c else 'no case':24} {done}")
    return 0


def main(argv=None) -> int:
    a = list(argv if argv is not None else sys.argv[1:])
    if not a:
        print(__doc__)
        return 1
    if a[0] == "status":
        return status()
    if a[0] == "rerun-research":
        for code in (c.upper() for c in a[1:]):
            rerun_research(code)
        return 0
    if a[0] == "rerun-service":
        for code in (c.upper() for c in a[1:]):
            rerun_teaching(code, reason="service scored again", component="service", rubric_id=2)
        return 0
    if a[0] == "rerun-teaching":
        for code in (c.upper() for c in a[1:]):
            rerun_teaching(code)
        return 0
    if a[0] == "collect":
        for code in (c.upper() for c in a[1:]):
            data = collect(code)
            old = RESULTS / f"{code}.json"
            run = RESULTS / f"{code}_run.json"
            data["run"] = json.loads(run.read_text(encoding="utf-8")) if run.exists() else (
                json.loads(old.read_text(encoding="utf-8")).get("run") if old.exists() else None)
            print(_save(code, data))
        return 0
    for code in (c.upper() for c in a):
        submit(code, log=lambda m: print(m, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
