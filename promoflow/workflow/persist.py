"""Saves an agent's `AgentOutput` into the database tables (shared by every agent, so each one only has to return
the agreed format). Computed results go here and never overwrite what the applicant entered.

Why a separate file? An agent's job is to JUDGE, not to know the database layout. Every agent returns the same
`AgentOutput` (see schemas.py), and this one function turns it into rows: agent_run, agent_assessment,
criterion_result, item_result, rubric_score, claim and flag."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from promoflow.db.enums import RubricCode, RunStatus
from promoflow.db.models import (
    AgentAssessment, AgentRun, Claim, CriterionResult, Flag, ItemResult, PromotionCase, Rubric, RubricItem,
    AuditLogEntry, RubricOpinion, RubricScore,
)
from promoflow.workflow.schemas import AgentOutput


def _dec(value: float | None) -> Decimal | None:
    """The database stores exact decimals; agents work with floats. Going through str() avoids 0.1+0.2 style noise."""
    return None if value is None else Decimal(str(value))


def _save_rubric(s: Session, case_id: int, run_id: int, out: AgentOutput) -> None:
    """The agent's suggested points. One row per case and rubric item: a re-evaluation (after a revision) replaces the
    suggestion and clears the HoD's and Dean's earlier points, because they approved a different dossier."""
    policy_version_id = s.get(PromotionCase, case_id).policy_version_id
    for line in out.rubric:
        # Find the official form line ("item 3 of the teaching rubric") this suggestion belongs to.
        item = s.scalar(select(RubricItem).join(Rubric, Rubric.id == RubricItem.rubric_id).where(
            Rubric.policy_version_id == policy_version_id, Rubric.code == RubricCode(line.rubric),
            RubricItem.item_no == line.item_no))
        # Update the row if this case already has one for the item, otherwise create it (an "upsert").
        row = s.scalar(select(RubricScore).where(RubricScore.case_id == case_id,
                                                 RubricScore.rubric_item_id == item.id))
        if row is None:
            row = RubricScore(case_id=case_id, rubric_item_id=item.id)
            s.add(row)
        row.suggested_points = _dec(line.suggested_points)
        row.suggested_by_run_id = run_id
        row.suggestion_basis = line.basis
        row.suggestion_rationale = line.rationale
        row.confidence = line.confidence
        # Chained assignment: set all of these to None at once (the reviewers must score the new suggestion afresh).
        row.hod_points = row.hod_user_id = row.hod_at = None
        row.dean_points = row.dean_user_id = row.dean_at = row.change_reason = None
        # Committee opinions: replace the earlier run's opinions with this run's (none when one model was used).
        s.flush()                                    # the row needs its id before opinions can point at it
        s.execute(delete(RubricOpinion).where(RubricOpinion.rubric_score_id == row.id))
        for o in line.opinions:
            s.add(RubricOpinion(rubric_score_id=row.id, model_name=o.model_name[:100], points=_dec(o.points),
                                rationale=o.rationale, confidence=o.confidence.value if o.confidence else None))
        # The permanent record: which model gave how many points to which rubric line of which case. The tables above are
        # replaced on every re-run; these audit rows (hash-chained, see db/seal.py) are never edited or removed.
        for model, pts, why, conf in ([(o.model_name, o.points, o.rationale, o.confidence.value if o.confidence else None) for o in line.opinions]
                                      or [(out.model_name, line.suggested_points, line.rationale, line.confidence)]):
            s.add(AuditLogEntry(user_id=None, case_id=case_id, action="model_score", entity_table="rubric_score", entity_id=row.id,
                                after={"model": model, "run_id": run_id, "rubric": str(line.rubric), "item_no": line.item_no,
                                       "points": None if pts is None else float(pts), "confidence": getattr(conf, "value", conf),
                                       "rationale": why}))


def save_output(s: Session, case_id: int, out: AgentOutput) -> int:
    """One agent_run + agent_assessment with its criteria, items, rubric lines, claims and flags.
    Returns the assessment id. `s` is an open database session; the caller commits (session_scope does it)."""
    # agent_run = "this agent ran once, at this time, with this model and prompt version" (for reproducibility).
    run = AgentRun(case_id=case_id, component=out.component, status=RunStatus.SUCCEEDED,
                   finished_at=datetime.now(timezone.utc), model_name=out.model_name,
                   prompt_version=out.prompt_version)
    s.add(run)
    s.flush()        # flush = send to the database now so `run.id` exists, without committing yet
    # agent_assessment = the result of that run: the verdict and the written narrative.
    assessment = AgentAssessment(case_id=case_id, agent_run_id=run.id, component=out.component,
                                 verdict=out.verdict, narrative=out.narrative)
    s.add(assessment)
    s.flush()
    # The detail rows all point back at the assessment through `assessment_id`.
    for c in out.criteria:
        s.add(CriterionResult(assessment_id=assessment.id, criterion_key=c.key, label=c.label[:200],
                              required_value=_dec(c.required), actual_value=_dec(c.actual), passed=c.passed,
                              policy_ref=c.policy_ref))
    for i in out.items:
        s.add(ItemResult(assessment_id=assessment.id, entity_table=i.entity_table, entity_id=i.entity_id,
                         counted=i.counted, classification=i.classification, credited_role=i.credited_role,
                         basis=i.basis, confidence=i.confidence, reason=i.reason))
    if out.rubric:
        _save_rubric(s, case_id, run.id, out)
    for c in out.claims:
        s.add(Claim(assessment_id=assessment.id, text=c.text, value=_dec(c.value), source_table=c.source_table,
                    source_ids=c.source_ids, verified=c.verified))
    for f in out.flags:
        s.add(Flag(case_id=case_id, assessment_id=assessment.id, severity=f.severity, code=f.code,
                   message=f.message, entity_table=f.entity_table, entity_id=f.entity_id))
    s.flush()
    return assessment.id
