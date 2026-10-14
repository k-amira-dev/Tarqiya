"""Saves an agent's `AgentOutput` into the database tables (shared by every agent, so each one only has to return
the agreed format). Computed results go here and never overwrite what the applicant entered."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import RubricCode, RunStatus
from promoflow.db.models import (
    AgentAssessment, AgentRun, Claim, CriterionResult, Flag, ItemResult, PromotionCase, Rubric, RubricItem,
    RubricScore,
)
from promoflow.workflow.schemas import AgentOutput


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _save_rubric(s: Session, case_id: int, run_id: int, out: AgentOutput) -> None:
    """The agent's suggested points. One row per case and rubric item: a re-evaluation (after a revision) replaces the
    suggestion and clears the HoD's and Dean's earlier points, because they approved a different dossier."""
    policy_version_id = s.get(PromotionCase, case_id).policy_version_id
    for line in out.rubric:
        item = s.scalar(select(RubricItem).join(Rubric, Rubric.id == RubricItem.rubric_id).where(
            Rubric.policy_version_id == policy_version_id, Rubric.code == RubricCode(line.rubric),
            RubricItem.item_no == line.item_no))
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
        row.hod_points = row.hod_user_id = row.hod_at = None
        row.dean_points = row.dean_user_id = row.dean_at = row.change_reason = None


def save_output(s: Session, case_id: int, out: AgentOutput) -> int:
    """One agent_run + agent_assessment with its criteria, items, claims and flags. Returns the assessment id.
    Rubric lines (Teaching/Service) are saved by those agents once the rubric_score mapping is written."""
    run = AgentRun(case_id=case_id, component=out.component, status=RunStatus.SUCCEEDED,
                   finished_at=datetime.now(timezone.utc), model_name=out.model_name,
                   prompt_version=out.prompt_version)
    s.add(run)
    s.flush()
    assessment = AgentAssessment(case_id=case_id, agent_run_id=run.id, component=out.component,
                                 verdict=out.verdict, narrative=out.narrative)
    s.add(assessment)
    s.flush()
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
