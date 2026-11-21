"""The scoring engine shared by the Teaching Agent (Appendix E) and the Service Agent (Appendix F).

Both appendices give point *ranges* and leave the choice inside a range to the promotion committee's judgment. An agent
supplies its evidence, its written scoring guidance and which items are scored by rule; this module does the rest, the
same way every time:

- items with no evidence score 0 and are flagged; items scored by rule use the points the agent computed;
- all other items go to the language model in ONE call, with written anchors, and each score must cite evidence by
  handle (`ss-12`) and fall inside the item's range (out-of-range points are clamped and flagged);
- every citation is checked by verify_claims(): a bad citation gets one retry, then the claim is marked unverified,
  the item's confidence drops to low and a person is flagged;
- if the model is unavailable the verdict is INCOMPLETE and nothing is guessed;
- the total is capped at the rubric total, compared with the pass mark, and turned into a verdict.

Names are never part of the evidence an agent builds. The agent only *suggests*: the Head of Department and the Dean
confirm or change each score (rubric_score keeps all three)."""
import json
import logging
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.config import COMMITTEE_INPUT_BUDGETS, COMMITTEE_SPREAD
from promoflow.db.enums import (
    Component, Confidence, DecisionBasis, FlagSeverity, PromotionTrack, RubricCode, Verdict,
)
from promoflow.db.models import PromotionCase, Rubric, RubricItem
from promoflow.workflow import guard
from promoflow.workflow.retry import _retry_wait
from promoflow.workflow import llm as llm_module
from promoflow.workflow.schemas import AgentOutput, CriterionOut, FlagOut, ManipulationReport, OpinionOut, RubricLineOut
from promoflow.workflow.verify import claims_from_citations, parse_handles, verify_claims


# The shape of ONE score the language model must return. Pydantic checks it, so an answer with a missing or invalid
# field is rejected instead of silently accepted.
class ItemJudgment(BaseModel):
    item_no: int
    points: float
    rationale: str
    cited: list[str] = Field(default_factory=list)
    confidence: Confidence


# The model's whole answer: one ItemJudgment per rubric item. `llm.with_structured_output(Judgment)` makes the model
# reply in exactly this shape.
class Judgment(BaseModel):
    items: list[ItemJudgment]
    manipulation_reported: list[ManipulationReport] = Field(default_factory=list)   # instructions found in the evidence and ignored


@dataclass(frozen=True)
class Profile:
    """Everything that differs between the agents."""
    component: Component
    rubric_code: RubricCode
    title: str                          # e.g. "Teaching total (Appendix E)"
    policy_ref: str                     # e.g. "Appendix E"
    system: str                         # the model's instructions
    guidance: dict[int, str]            # written scoring anchors per item
    prompt_version: str
    fixed_items: tuple[int, ...]        # scored by rule, not by the model
    llm_items: tuple[int, ...]          # scored by the model, when there is evidence
    assumption_note: str                # shown to reviewers: which choices are assumptions
    shared_for: tuple[int, ...] = ()    # items that may also draw on the context's shared evidence (Service)
    optional_items: tuple[int, ...] = ()  # items whose missing evidence is information, not a warning


@dataclass
class Spec:
    item_no: int
    text: str
    min_points: float
    max_points: float
    full_only: bool
    redistributable: bool


@dataclass
class Context:
    case_id: int
    track: PromotionTrack
    specs: list[Spec]
    total_points: float
    pass_points: float
    evidence: dict[int, dict] = field(default_factory=dict)       # item_no -> {"records": [...], "summary": {...}}
    fixed: dict[int, tuple[float, str, list[str]]] = field(default_factory=dict)   # item_no -> (points, why, handles)
    shared: list[dict] = field(default_factory=list)              # records that several items may cite
    checks: list[CriterionOut] = field(default_factory=list)      # deterministic presence/count checks

    def applicable(self) -> list[Spec]:
        return [s for s in self.specs if not (s.full_only and self.track != PromotionTrack.TO_FULL)]


# Step 0 of every rubric agent: read the rubric (its items, ranges, total and pass mark) from the database for THIS
# case's policy version. The agent then adds its own evidence to the returned Context.
def load_context(s: Session, case_id: int, code: RubricCode) -> Context:
    """The rubric's items, total and pass mark for this case's policy version. The agent adds the evidence."""
    case = s.get(PromotionCase, case_id)
    rubric = s.scalar(select(Rubric).where(Rubric.policy_version_id == case.policy_version_id, Rubric.code == code))
    specs = [Spec(i.item_no, i.text_en, float(i.min_points), float(i.max_points), i.full_professor_only,
                  i.redistributable)
             for i in s.scalars(select(RubricItem).where(RubricItem.rubric_id == rubric.id)
                                .order_by(RubricItem.item_no))]
    return Context(case_id, case.track, specs, float(rubric.total_points), float(rubric.pass_points))


# Turn a list of handles ("ss-1", "ss-2", "po-4") into {table: {ids}}, the form verify_claims() expects.
def _allowed_from(handles: list[str]) -> dict[str, set[int]]:
    by_table, _ = parse_handles(handles)
    return {table: set(ids) for table, ids in by_table.items()}


# The evidence the model is allowed to cite for one item: that item's own records, plus the shared records when the
# item may use them (Service agent only).
def _allowed(item_no: int, ctx: Context, profile: Profile) -> dict[str, set[int]]:
    handles = [r["handle"] for r in ctx.evidence[item_no]["records"]]
    if item_no in profile.shared_for:
        handles += [r["handle"] for r in ctx.shared]
    return _allowed_from(handles)


def _missing(item_no: int, profile: Profile) -> FlagSeverity:
    return FlagSeverity.INFO if item_no in profile.optional_items else FlagSeverity.WARNING


def _has_evidence(item_no: int, ctx: Context, profile: Profile) -> bool:
    return bool(ctx.evidence[item_no]["records"]) or (item_no in profile.shared_for and bool(ctx.shared))


# Records of one kind share the same fields, so spelling the field names out for every record wastes most of the request (64 student
# reports were 8,000 characters). Each group of records with the same fields is sent as one table: the column names once, then one
# short row per record. The first column is always the handle the model must cite.
def _tables(records: list[dict]) -> list[dict]:
    tables: list[dict] = []
    for r in records:
        keys = list(r)
        if tables and tables[-1]["columns"] == keys:
            tables[-1]["rows"].append([r[k] for k in keys])
        else:
            tables.append({"columns": keys, "rows": [[r[k] for k in keys]]})
    return tables


# Build the two messages sent to the model: the fixed instructions (system) and the evidence for every item to
# score, as JSON (human). When a previous attempt had problems, they are appended so the model can fix them.
def _messages(ctx: Context, profile: Profile, items: list[Spec], feedback: list[str] | None):
    payload = {"promotion_track": ctx.track.value, "items": [
        {"item_no": i.item_no, "criterion": i.text,
         "allowed_points": [0 if i.min_points == i.max_points else i.min_points, i.max_points],
         "guidance": profile.guidance[i.item_no], "summary": ctx.evidence[i.item_no]["summary"],
         "evidence": _tables(ctx.evidence[i.item_no]["records"])} for i in items]}
    payload["evidence_format"] = ("Evidence is given as tables: \"columns\" names the fields once and each row is one record in that order. "
                                  "The \"handle\" field of a row is what you cite.")
    if ctx.shared and any(i.item_no in profile.shared_for for i in items):
        payload["shared_evidence"] = {
            "usable_for_items": [i.item_no for i in items if i.item_no in profile.shared_for],
            "note": "Each of these activities may support ONE item only. Cite it under the item where it fits best.",
            "records": _tables(ctx.shared)}
    user = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    if feedback:
        user += "\n\nYour previous answer had these problems. Fix them:\n" + "\n".join(f"- {p}" for p in feedback)
    return [("system", profile.system), ("human", user)]


def _lowest(spec: Spec) -> float:
    return 0.0 if spec.min_points == spec.max_points else spec.min_points


def _claims_nothing(j: ItemJudgment, spec: Spec) -> bool:
    """0 points with no citation, on an item that can score 0, means 'nothing in the evidence applies': a valid
    answer with nothing to verify. On an item whose range starts above 0 it is not."""
    return j.points == 0 and not j.cited and _lowest(spec) == 0


# Check a model answer: every item must be present and every citation must be real. Returns the list of problems
# (empty list = the answer is good).
def _problems(judged: dict[int, ItemJudgment], items: list[Spec], ctx: Context, profile: Profile) -> list[str]:
    problems = []
    for spec in items:
        j = judged.get(spec.item_no)
        if j is None:
            problems.append(f"Item {spec.item_no} is missing. Return an entry for every item.")
            continue
        if _claims_nothing(j, spec):
            continue
        claims = claims_from_citations(j.rationale, j.points, j.cited)
        problems += [f"Item {spec.item_no}: {p} Cite only handles listed in that item's evidence or in the shared "
                     "evidence." for p in verify_claims(claims, _allowed(spec.item_no, ctx, profile))]
    return problems


# Some models (qwen on Groq) answer in their own tool-call format, `<function=Judgment><parameter=items>[ ... ]`, which Groq rejects with
# "tool call validation failed" although the answer itself is complete. The rejection carries the text the model wrote (`failed_generation`);
# read the items from it and check them exactly like a normal answer (the same schema, then the same citation and range checks).
def _salvage(error: Exception) -> "Judgment | None":
    body = getattr(error, "body", None)
    err = (body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else body) or {}
    text = err.get("failed_generation") if isinstance(err, dict) else None
    if not isinstance(text, str):
        return None
    m = re.search(r"<parameter=items>\s*(\[.*\])\s*</\s*parameter>", text, re.S)
    if not m:
        return None
    try:
        raw = json.loads(m.group(1))
        items: dict[int, ItemJudgment] = {}
        for r in raw:
            j = ItemJudgment.model_validate(r)
            if j.item_no not in items or (j.cited and not items[j.item_no].cited):     # a repeated item: keep the one that cites its evidence
                items[j.item_no] = j
        return Judgment(items=list(items.values())) if items else None
    except Exception:
        return None


def _invoke(llm, messages, attempts: int = 5):
    """One structured model call. When the provider says "too many tokens this minute" (Teaching, Service and Research all ask at about the
    same time and share one allowance), wait as long as it says and ask again, instead of giving up on the first refusal."""
    for attempt in range(attempts):
        try:
            return llm.with_structured_output(Judgment).invoke(messages)
        except Exception as e:
            if "tool_use_failed" in f"{e}" and (salvaged := _salvage(e)) is not None:
                logging.getLogger(__name__).warning("Read the model's answer from its rejected tool call (%d item(s)).", len(salvaged.items))
                return salvaged
            wait = _retry_wait(e, attempt)
            if wait is None or attempt == attempts - 1:
                raise
            time.sleep(wait)


# Ask ONE model about every item. If its answer has problems we ask once more with the problems listed; after that we
# stop and the caller marks what is still wrong as unverified. Returns (answers by item, error text or None).
def _ask_batch(llm, ctx: Context, profile: Profile, to_judge: list[Spec], reports: list | None = None) -> tuple[dict[int, ItemJudgment], str | None]:
    judged: dict[int, ItemJudgment] = {}
    feedback = None
    seen: list = []          # what the model reported in its last good answer
    for _attempt in (1, 2):                          # one retry, then the claims are marked unverified
        try:
            result = _invoke(llm, _messages(ctx, profile, to_judge, feedback))
        except Exception as e:                        # network, rate limit, bad output: say so, do not guess
            return judged, f"{type(e).__name__}: {e}"
        wanted = {s.item_no for s in to_judge}
        judged = {j.item_no: j for j in result.items if j.item_no in wanted}
        seen = list(result.manipulation_reported)
        feedback = _problems(judged, to_judge, ctx, profile)
        if not feedback:
            break
    if reports is not None:
        reports.extend(seen)
    return judged, None


def _budget(label: str) -> int | None:
    """The input-token budget for a model from COMMITTEE_INPUT_BUDGETS ("name=tokens,..."), or None = no limit."""
    for part in COMMITTEE_INPUT_BUDGETS.split(","):
        name, _, tokens = part.partition("=")
        if name.strip() == label and tokens.strip().isdigit():
            return int(tokens)
    return None


# Items are scored independently, so a model with a small context window can take them in several requests. Pack items, in order, into
# batches whose request stays within `budget` tokens (estimated as characters / 3.5). An item too big for the budget goes alone.
def _batches(ctx: Context, profile: Profile, to_judge: list[Spec], budget: int | None) -> list[list[Spec]]:
    if not budget:
        return [to_judge]
    def tokens(items):
        return sum(len(m[1]) for m in _messages(ctx, profile, items, None)) / 3.5
    batches: list[list[Spec]] = []
    for spec in to_judge:
        if batches and tokens(batches[-1] + [spec]) <= budget:
            batches[-1].append(spec)
        else:
            batches.append([spec])
    return batches


# Ask ONE model about every item (in one request, or in batches when the model has a small window). A batch that fails is reported and
# the items in the other batches are still kept. Returns (answers by item, error text or None).
def _ask(llm, ctx: Context, profile: Profile, to_judge: list[Spec], label: str = "", reports: list | None = None) -> tuple[dict[int, ItemJudgment], str | None]:
    judged: dict[int, ItemJudgment] = {}
    errors: list[str] = []
    for batch in _batches(ctx, profile, to_judge, _budget(label)):
        got, err = _ask_batch(llm, ctx, profile, batch, reports)
        judged.update(got)
        if err:
            errors.append(err)
    return judged, "; ".join(errors) or None


# Several models answered. For each item take the MEDIAN of their points (rounded to half a point), keep the answer closest to it as
# the one shown (so the rationale and citations are a real model's), and remember everyone's opinion.
def _consolidate(answers: dict[str, dict[int, ItemJudgment]]) -> tuple[dict[int, ItemJudgment], dict[int, list[tuple[str, ItemJudgment]]]]:
    merged: dict[int, ItemJudgment] = {}
    opinions: dict[int, list[tuple[str, ItemJudgment]]] = {}
    items = {n for judged in answers.values() for n in judged}
    for n in sorted(items):
        votes = [(label, judged[n]) for label, judged in answers.items() if n in judged]
        opinions[n] = votes
        mid = round(statistics.median(j.points for _, j in votes) * 2) / 2
        _, rep = min(votes, key=lambda v: abs(v[1].points - mid))       # ties: the first model listed
        merged[n] = rep.model_copy(update={"points": mid})
    return merged, opinions


def assess(ctx: Context, llm, profile: Profile, committee: list[tuple[str, object]] | None = None) -> AgentOutput:
    """Score the case. `llm` is anything with .with_structured_output(model).invoke(messages); None = unavailable.
    `committee` = [(label, llm), ...] with two or more models: each one scores every item, the median is the suggestion
    and a wide spread is flagged for a person. Without it the single `llm` is used, exactly as before."""
    flags: list[FlagOut] = []
    lines: list[RubricLineOut] = []
    claims = []
    rubric = profile.rubric_code.value
    applicable = ctx.applicable()
    # Items that go to the language model: not scored by rule, AND having some evidence to judge.
    to_judge = [s for s in applicable if s.item_no in profile.llm_items and _has_evidence(s.item_no, ctx, profile)]
    members = committee if committee and len(committee) >= 2 else None
    opinions: dict[int, list[tuple[str, ItemJudgment]]] = {}

    # Text in the applicant's own entries that reads like an instruction to the model: keep it (it is evidence), but a person must read the case.
    suspicious = [(n, h, hits) for n, e in ctx.evidence.items() for h, hits in guard.scan_records(e["records"])] +                  [(0, h, hits) for h, hits in guard.scan_records(ctx.shared)]
    if suspicious:
        where = "; ".join(f"{h} ({', '.join(hits)})" for _n, h, hits in suspicious[:6])
        flags.append(FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="possible_prompt_injection",
                             message=f"Text in the applicant's entries looks like an instruction to the scoring model: {where}. "
                                     "A person must read it, and the suggested scores should not be trusted until then."))

    # STEP 1 - ask the model(s), once for all items.
    judged: dict[int, ItemJudgment] = {}
    llm_error = None
    reports: list = []                      # instructions the model(s) found in the evidence and ignored
    if to_judge and members:
        # Each model has its own rate limit, so they can be asked at the same time.
        with ThreadPoolExecutor(max_workers=len(members)) as pool:
            replies = list(pool.map(lambda m: _ask(m[1], ctx, profile, to_judge, m[0], reports), members))
        answers = {}
        for (label, _m), (got, err) in zip(members, replies):
            if err:
                flags.append(FlagOut(severity=FlagSeverity.WARNING, code="committee_member_failed",
                                     message=f"Model {label} gave no score and was left out: {err}"))
            if got:
                answers[label] = got
        if answers:
            judged, opinions = _consolidate(answers)
        else:
            llm_error = "No committee model returned a score."
    elif to_judge and llm is None:
        llm_error = "No language model is configured (set GROQ_API_KEY)."
    elif to_judge:
        judged, llm_error = _ask(llm, ctx, profile, to_judge, "", reports)
    flags += guard.flags_from_reports(reports)
    if llm_error:
        flags.append(FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="llm_unavailable",
                             message=f"The judgment items could not be scored: {llm_error}"))

    # STEP 2 - build one line of the rubric for every applicable item, in order. Each item takes exactly one of four
    # routes: (a) scored by rule; (b) no evidence, so 0 points; (c) the model gave no answer for it; (d) the model's
    # score, kept inside the allowed range and with its citations verified.
    for spec in applicable:
        n = spec.item_no
        # Route (a): the agent computed these points by rule, so no model is involved.
        if n in profile.fixed_items:
            points, why, cited = ctx.fixed[n]
            if not cited:
                flags.append(FlagOut(severity=_missing(n, profile), code=f"no_evidence_item_{n}",
                                     message=f"No evidence entered for item {n}: {spec.text}. Scored 0."))
            lines.append(RubricLineOut(rubric=rubric, item_no=n, suggested_points=points, rationale=why,
                                       basis=DecisionBasis.RULE, confidence=Confidence.MEDIUM))
            if cited:                                  # rule-based, but still checked against the evidence list
                rule_claims = claims_from_citations(f"Item {n}: {why}", points, cited)
                verify_claims(rule_claims, _allowed_from(cited))
                claims += rule_claims
            continue
        # Route (b): nothing to judge. 0 points, and a flag so a person knows the applicant entered nothing here.
        if not _has_evidence(n, ctx, profile):
            flags.append(FlagOut(severity=_missing(n, profile), code=f"no_evidence_item_{n}",
                                 message=f"No evidence entered for item {n}: {spec.text}. Scored 0."
                                         + (" Points for advising may be redistributed for departments without "
                                            "graduate degrees." if spec.redistributable else "")))
            lines.append(RubricLineOut(rubric=rubric, item_no=n, suggested_points=0.0,
                                       rationale="No evidence entered.", basis=DecisionBasis.RULE,
                                       confidence=Confidence.HIGH))
            continue
        # Routes (c) and (d): look up the model's judgment for this item.
        j = judged.get(n)
        if j is None:
            lines.append(RubricLineOut(rubric=rubric, item_no=n, suggested_points=0.0,
                                       rationale="Not scored: no judgment was returned.", basis=DecisionBasis.LLM,
                                       confidence=Confidence.LOW))
            if not llm_error:
                flags.append(FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="judgment_missing",
                                     message=f"No judgment was returned for item {n}: {spec.text}."))
            continue
        # Keep the points inside the item's range. If the model went outside it, fix the number AND raise a flag, so
        # the change is never silent.
        lo = _lowest(spec)
        points = min(max(j.points, lo), spec.max_points)
        if points != j.points:
            flags.append(FlagOut(severity=FlagSeverity.WARNING, code="points_clamped",
                                 message=f"Item {n}: the suggested {j.points:g} points was outside the allowed range "
                                         f"{lo:g}-{spec.max_points:g} and was set to {points:g}."))
        item_claims = [] if _claims_nothing(j, spec) else claims_from_citations(f"Item {n}: {j.rationale}", points, j.cited)
        unverified = verify_claims(item_claims, _allowed(n, ctx, profile))
        confidence = Confidence.LOW if unverified else j.confidence
        if unverified:
            flags.append(FlagOut(severity=FlagSeverity.WARNING, code="unverified_claim",
                                 message=f"Item {n}: the rationale cites evidence that could not be verified. "
                                         "Check it before relying on this score."))
        claims += item_claims
        votes = opinions.get(n, [])
        shown = [OpinionOut(model_name=label, points=min(max(v.points, lo), spec.max_points), rationale=v.rationale,
                            confidence=v.confidence) for label, v in votes]
        spread = max(o.points for o in shown) - min(o.points for o in shown) if len(shown) > 1 else None
        # The models disagree when their points are further apart than COMMITTEE_SPREAD of the item's range (at least 1 point).
        if spread is not None and spread > max(1.0, COMMITTEE_SPREAD * (spec.max_points - lo)):
            flags.append(FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="committee_disagreement",
                                 message=f"Item {n}: the models disagree ({', '.join(f'{o.model_name} {o.points:g}' for o in shown)}). "
                                         f"The suggestion is the median, {points:g}; a person should decide."))
        lines.append(RubricLineOut(rubric=rubric, item_no=n, suggested_points=points, rationale=j.rationale,
                                   basis=DecisionBasis.LLM, confidence=confidence, opinions=shown, spread=spread))

    # A shared activity may support only one item: citing it under two items would count it twice.
    if ctx.shared:
        shared_handles = {r["handle"] for r in ctx.shared}
        used: dict[str, list[int]] = {}
        for n, j in judged.items():
            for h in {c.strip().lower() for c in j.cited} & shared_handles:
                used.setdefault(h, []).append(n)
        for h, items in used.items():
            if len(items) > 1:
                flags.append(FlagOut(severity=FlagSeverity.WARNING, code="double_counted",
                                     message=f"Activity {h} is cited for items {sorted(items)}. It should support one "
                                             "item only; please check the scores."))

    # STEP 3 - add up the points. The total can never exceed the rubric total (the form's own item maximums add up
    # to more than its stated total, which is a policy question we flag).
    raw_total = sum(l.suggested_points for l in lines)
    total = min(raw_total, ctx.total_points)
    if raw_total > ctx.total_points:
        flags.append(FlagOut(severity=FlagSeverity.INFO, code="total_capped",
                             message=f"The item maximums add up to more than {ctx.total_points:g}; the total is "
                                     f"capped at {ctx.total_points:g}. (Policy question for the committee.)"))
    flags.append(FlagOut(severity=FlagSeverity.INFO, code="assumed_scoring_guidance",
                         message=profile.assumption_note.format(version=profile.prompt_version)))

    # STEP 4 - the rows reviewers see in the report: the total against the pass mark, any agent-specific checks,
    # then one row per item.
    by_no = {s.item_no: s for s in applicable}
    criteria = [CriterionOut(key=f"{rubric}_total", label=profile.title, required=ctx.pass_points, actual=total,
                             max_value=ctx.total_points, passed=total >= ctx.pass_points, policy_ref=profile.policy_ref)]
    criteria += ctx.checks
    criteria += [CriterionOut(key=f"item_{l.item_no}", label=f"Item {l.item_no}: {by_no[l.item_no].text}"[:200],
                              required=by_no[l.item_no].min_points, actual=l.suggested_points,
                              max_value=by_no[l.item_no].max_points, passed=l.suggested_points >= by_no[l.item_no].min_points and l.suggested_points > 0,
                              policy_ref=profile.policy_ref) for l in lines]

    # STEP 5 - the verdict. INCOMPLETE if the model was unavailable; NEEDS_HUMAN if any score is low-confidence or a
    # flag asks for a person; otherwise a plain PASS or FAIL against the pass mark. A shaky score never becomes a
    # confident PASS or FAIL.
    shaky = any(l.confidence == Confidence.LOW for l in lines)
    if llm_error:
        verdict = Verdict.INCOMPLETE
    elif shaky or any(f.severity == FlagSeverity.NEEDS_HUMAN for f in flags):
        verdict = Verdict.NEEDS_HUMAN
    else:
        verdict = Verdict.PASS if total >= ctx.pass_points else Verdict.FAIL

    # STEP 6 - the written assessment: the total, then every item's points and reason.
    narrative = (f"Suggested total {total:g} of {ctx.total_points:g} ({total / ctx.total_points:.0%}); pass mark "
                 f"{ctx.pass_points:g}. " + " ".join(f"Item {l.item_no}: {l.suggested_points:g} - {l.rationale}"
                                                      for l in lines))
    return AgentOutput(component=profile.component, verdict=verdict, narrative=narrative, criteria=criteria,
                       rubric=lines, claims=claims, flags=flags,
                       confidence=Confidence.LOW if shaky or llm_error else Confidence.MEDIUM,
                       model_name=((("committee: " + " + ".join(label for label, _ in members))[:100] if members
                                    else llm_module.model_name()) if to_judge else None),
                       prompt_version=profile.prompt_version)
