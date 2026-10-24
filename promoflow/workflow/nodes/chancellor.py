"""Chancellor's Office Agent: shortlist of up to 10 external referees with conflict-of-interest checks.
Owner: Khadidja. STUB for now. The Chancellor selects; the agent never approves.

HOW IT FITS IN: this node runs AFTER the Dean has approved the case. It prepares a shortlist of candidate referees
and stores it in `state["shortlist"]`. The graph then pauses (graph.py, `referee_selection`) and shows the shortlist
to the Chancellor, who picks the referees. Nothing here decides anything: it only prepares the choice.

TO DO (real version): search for candidates (OpenAlex / Scopus), remove conflicts of interest (co-authorship, same
institution, a referee used in the last 5 years), keep at most 10, and save them as `referee_candidate` rows. Send the
language model ids and facts only, never names. The output stays `{"shortlist": [...]}` so the graph and the
Chancellor's page need no change."""
from promoflow.workflow.schemas import CaseState

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from promoflow import config
from promoflow.db import session as db_session
from promoflow.db.enums import Component, Confidence, DecisionBasis, FlagSeverity, Verdict
from promoflow.db.models import (
    PromotionCase, PromotionCriteria, Publication, PublicationAuthor, Referee, RefereeCandidate,
    ReviewerAssignment, ScopusEvidence,
)
from promoflow.rules import referees as rules
from promoflow.workflow import llm as llm_module
from promoflow.workflow import scholarly
from promoflow.workflow.nodes import use_stubs
from promoflow.workflow.persist import save_output
from promoflow.workflow.schemas import AgentOutput, CaseState, FlagOut, ItemOut

SYSTEM = """You are the Chancellor's Office Agent of PromoFlow (faculty promotion, University of Sharjah). You rank
candidate external referees for a promotion case by how well their research matches the applicant's field. All
candidates have already passed the conflict-of-interest and eligibility rules.
### SCORING RUBRIC (0.0 to 1.0)
- 1.0: Exact narrow specialization match (identical domain, methods, or core research topics).
- 0.7: High overlap (same subfield or closely related methodology).
- 0.5: Broad field match (same general discipline/department, but different subfield).
- 0.2: Marginal relevance (tangential connection or minor overlap).
- 0.0: Unrelated field.

### CRITICAL CONSTRAINTS
1. Base scores strictly on topic alignment with applicant specialization and paper titles. not institutional prestige, geographic location, or candidate fame.
2. Rely strictly on the provided context. Do NOT use outside knowledge or hallucinate publication history.
3. Keep each rationale concise (maximum 30 words).
4. Do NOT omit any candidate referee provided in the input

### OUTPUT FORMAT
Return a rationale of at most 30 words valid JSON only with no markdown formatting or commentary outside the JSON array:
[
  {
    "handle": "c-3",
    "score": 0.85,
    "rationale": "Direct overlap in deep learning for medical imaging, matching three of the applicant's primary journal publications."
  }
]
"""


def run(state: CaseState) -> dict:
    # Placeholder candidates (ids only). Real version: OpenAlex/Scopus search + COI checks -> referee_candidate rows.
    return {"shortlist": [{"candidate_id": i, "coi_clear": True} for i in range(1, 4)]}


