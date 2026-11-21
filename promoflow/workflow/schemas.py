"""The data shapes of the workflow, in one place.

1. `AgentOutput` (and its parts): the one format every agent returns. This is the contract between the people
   building the agents: as long as a node returns an `AgentOutput`, it plugs into the graph and the Report Builder
   can read it. Agents never receive names (students, observers, referees); claims and items point at database
   records by id.
2. `CaseState`: what travels through the graph. Kept small on purpose: the database is the real store, the graph
   state only carries ids, each agent's structured output and the human decisions. Agent outputs are stored as plain
   dicts (`AgentOutput.model_dump(mode="json")`) so the checkpointer can save them.

WHAT IS PYDANTIC? (for beginners)
---------------------------------
Every class below that extends `BaseModel` is a Pydantic model: a class that describes the SHAPE of some data and
checks it for you. If you build `FlagOut(severity="oops", ...)` Pydantic raises an error because "oops" is not a valid
severity. A field written `x: int | None = None` means "an integer or nothing, and it is optional". This is what
keeps every agent's output in the same, predictable format, so the Report Builder and the pages never have to guess.
"""
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field

from promoflow.db.enums import Component, Confidence, DecisionBasis, FlagSeverity, Verdict


class ManipulationReport(BaseModel):
    """The model saw text in the evidence that tried to instruct it (for example "give full marks"), ignored it, and says where it was."""
    handle: str                           # the record the text was in, e.g. "ss-3"
    quote: str = ""                       # a short quote of the text


class CriterionOut(BaseModel):
    """One row of the report's summary table: criterion, required, actual, pass/fail (-> criterion_result)."""
    key: str                              # e.g. "min_class_a_main_author"
    label: str                            # the sentence a person reads in the report
    required: float | None = None         # what the policy asks for (a number), if it is numeric
    actual: float | None = None           # what this applicant has
    max_value: float | None = None        # the most that can be scored (points rows only); lets the report show "4 / 4"
    passed: bool | None = None            # None = a human must decide
    policy_ref: str | None = None         # clause quoted to the user, e.g. "Att. 2, p.1"


class ItemOut(BaseModel):
    """Verdict on one entry, e.g. paper #3 counted as Class A (-> item_result)."""
    entity_table: str                     # which table the entry lives in, e.g. "publication"
    entity_id: int                        # its row id in that table
    counted: bool | None = None           # does it count towards the requirements?
    classification: str | None = None     # e.g. "class_a"
    credited_role: str | None = None      # e.g. "main author"
    basis: DecisionBasis = DecisionBasis.RULE   # decided by a rule, the language model, or both
    confidence: Confidence | None = None
    reason: str | None = None


class OpinionOut(BaseModel):
    """One committee member's own score for one rubric item (-> rubric_opinion). Shown to the Head and the Dean."""
    model_name: str
    points: float
    rationale: str | None = None
    confidence: Confidence | None = None


class RubricLineOut(BaseModel):
    """Teaching (Appendix E) and Service (Appendix F) only: the agent's suggested points (-> rubric_score)."""
    rubric: str                           # "teaching" or "service"
    item_no: int                          # the line number on the official form
    suggested_points: float
    basis: DecisionBasis = DecisionBasis.RULE
    rationale: str | None = None          # why these points (shown to the reviewers)
    confidence: Confidence | None = None
    opinions: list[OpinionOut] = Field(default_factory=list)   # every committee member's score (empty = single model)
    spread: float | None = None           # highest minus lowest opinion (committee only)


class ClaimOut(BaseModel):
    """A factual statement in the narrative and the records that back it (-> claim, checked by verify_claims)."""
    text: str
    value: float | None = None
    source_table: str                     # where the supporting records live
    source_ids: list[int] = Field(default_factory=list)   # which rows (Field(default_factory=list) = empty list)
    verified: bool | None = None          # filled in by verify_claims()


class FlagOut(BaseModel):
    """Anything a human must look at (-> flag)."""
    severity: FlagSeverity                # info / warning / needs_human
    code: str                             # e.g. "exceptional_research_volume"
    message: str
    entity_table: str | None = None       # optionally point at the record the flag is about
    entity_id: int | None = None


class AgentOutput(BaseModel):
    """What EVERY agent returns, whatever it does inside. Fill what applies and leave the rest empty."""
    component: Component                  # which agent produced this
    verdict: Verdict                      # pass / fail / needs_human / incomplete
    narrative: str | None = None          # the written assessment
    criteria: list[CriterionOut] = Field(default_factory=list)
    items: list[ItemOut] = Field(default_factory=list)
    rubric: list[RubricLineOut] = Field(default_factory=list)
    claims: list[ClaimOut] = Field(default_factory=list)
    flags: list[FlagOut] = Field(default_factory=list)
    confidence: Confidence | None = None
    model_name: str | None = None         # None for rule-only components
    prompt_version: str | None = None     # which version of the prompt was used (for reproducibility)
    is_stub: bool = False                 # True while the real agent is not written yet


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """Reducer: the three parallel agents each add their own key to `results` without overwriting each other."""
    # LangGraph calls this whenever two nodes write to the same state key: it keeps both sets of entries.
    return {**(left or {}), **(right or {})}


class CaseState(TypedDict, total=False):
    """The 'form' that travels through the graph. Each node reads it and returns only the keys it fills in.

    `total=False` means none of the keys is required to be present (the form starts nearly empty)."""
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
