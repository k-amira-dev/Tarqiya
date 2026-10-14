"""The data shapes of the workflow, in one place.

1. `AgentOutput` (and its parts): the one format every agent returns. This is the contract between the people
   building the agents: as long as a node returns an `AgentOutput`, it plugs into the graph and the Report Builder
   can read it. Agents never receive names (students, observers, referees); claims and items point at database
   records by id.
2. `CaseState`: what travels through the graph. Kept small on purpose: the database is the real store, the graph
   state only carries ids, each agent's structured output and the human decisions. Agent outputs are stored as plain
   dicts (`AgentOutput.model_dump(mode="json")`) so the checkpointer can save them."""
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field

from promoflow.db.enums import Component, Confidence, DecisionBasis, FlagSeverity, Verdict


class CriterionOut(BaseModel):
    """One row of the report's summary table: criterion, required, actual, pass/fail (-> criterion_result)."""
    key: str                              # e.g. "min_class_a_main_author"
    label: str
    required: float | None = None
    actual: float | None = None
    passed: bool | None = None            # None = a human must decide
    policy_ref: str | None = None         # clause quoted to the user, e.g. "Att. 2, p.1"


class ItemOut(BaseModel):
    """Verdict on one entry, e.g. paper #3 counted as Class A (-> item_result)."""
    entity_table: str
    entity_id: int
    counted: bool | None = None
    classification: str | None = None
    credited_role: str | None = None
    basis: DecisionBasis = DecisionBasis.RULE
    confidence: Confidence | None = None
    reason: str | None = None


class RubricLineOut(BaseModel):
    """Teaching (Appendix E) and Service (Appendix F) only: the agent's suggested points (-> rubric_score)."""
    rubric: str                           # "teaching" or "service"
    item_no: int
    suggested_points: float
    basis: DecisionBasis = DecisionBasis.RULE
    rationale: str | None = None
    confidence: Confidence | None = None


class ClaimOut(BaseModel):
    """A factual statement in the narrative and the records that back it (-> claim, checked by verify_claims)."""
    text: str
    value: float | None = None
    source_table: str
    source_ids: list[int] = Field(default_factory=list)
    verified: bool | None = None          # filled in by verify_claims()


class FlagOut(BaseModel):
    """Anything a human must look at (-> flag)."""
    severity: FlagSeverity
    code: str                             # e.g. "exceptional_research_volume"
    message: str
    entity_table: str | None = None
    entity_id: int | None = None


class AgentOutput(BaseModel):
    component: Component
    verdict: Verdict
    narrative: str | None = None
    criteria: list[CriterionOut] = Field(default_factory=list)
    items: list[ItemOut] = Field(default_factory=list)
    rubric: list[RubricLineOut] = Field(default_factory=list)
    claims: list[ClaimOut] = Field(default_factory=list)
    flags: list[FlagOut] = Field(default_factory=list)
    confidence: Confidence | None = None
    model_name: str | None = None         # None for rule-only components
    prompt_version: str | None = None
    is_stub: bool = False                 # True while the real agent is not written yet


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """Reducer: the three parallel agents each add their own key to `results` without overwriting each other."""
    return {**(left or {}), **(right or {})}


class CaseState(TypedDict, total=False):
    case_id: int
    options: dict[str, Any]                       # stub switches for tests/demo only, e.g. {"stub_eligible": False}
    results: Annotated[dict, merge_dicts]         # component name -> AgentOutput dict
    eligible: bool
    report: dict                                  # Report Builder output
    hod: dict                                     # {"outcome": "approve" | "return_for_revision", "comment", "sections"}
    dean: dict
    shortlist: list[dict]                         # Chancellor's Office candidates (ids, no names in the LLM)
    selected_referees: list[int]                  # the Chancellor's choice
    final_status: str                             # where the run ended, shown in the UI
