"""Chancellor's Office Agent: shortlist of up to 10 external referees with conflict-of-interest checks.
Owner: Khadidja. STUB for now. The Chancellor selects; the agent never approves.

HOW IT FITS IN: this node runs AFTER the Dean has approved the case. It prepares a shortlist of candidate referees
and stores it in `state["shortlist"]`. The graph then pauses (graph.py, `referee_selection`) and shows the shortlist
to the Chancellor, who picks the referees. Nothing here decides anything: it only prepares the choice.

TO DO (real version): search for candidates (OpenAlex / Scopus), remove conflicts of interest (co-authorship, same
institution, a referee used in the last 5 years), keep at most 10, and save them as `referee_candidate` rows. Send the
language model ids and facts only, never names. The output stays `{"shortlist": [...]}` so the graph and the
Chancellor's page need no change."""

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

PROMPT_VERSION = "referees-v1"
SEARCH_YEARS = 5
SEARCH_POOL = 40          # candidates fetched from OpenAlex before the rules filter them
COAUTHOR_YEARS = 10       # co-authorship window for the conflict-of-interest check 

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
  ### OUTPUT
  For EVERY candidate return its handle exactly as given (e.g. "c-3"), a score from 0.0 to 1.0, and a rationale of at
  most 30 words, in the "items" list.
"""

class Ranked(BaseModel):
    handle: str
    score: float
    rationale: str


class Ranking(BaseModel):
    items: list[Ranked] = Field(default_factory=list)
    
"""Everything the agent needs as plain data: the case, track, topic words, paper
titles, OpenAlex ID/ORCID, his side for the conflict checks (ApplicantSide ,Chapter 3), the referees used in the last 5 years, and how many reports the policy needs"""

@dataclass
class ShortlistContext:
    case_id: int
    track: str
    topic_terms: list[str]                       # specialization, fine specialization, keywords
    paper_titles: list[str]
    applicant_ref: str | None                    # OpenAlex id or ORCID from Section 0
    applicant: rules.ApplicantSide               # filled from the dossier; completed by applicant_profile()
    recently_used: set[str] = field(default_factory=set)        # OpenAlex ids used in the last 5 years
    min_reports: int = 3


def build_context(s: Session, case_id: int, now: datetime) -> ShortlistContext:
    case = s.get(PromotionCase, case_id)
    if case is None:
        raise ValueError(f"No case with id {case_id}.")
    crit = s.scalar(select(PromotionCriteria).where(PromotionCriteria.policy_version_id == case.policy_version_id,
                                                    PromotionCriteria.track == case.track))
    pubs = list(s.scalars(select(Publication).where(Publication.case_id == case_id,
                                                    Publication.submit_for_promotion.is_(True))))
    names = list(s.scalars(select(PublicationAuthor.display_name).where(
        PublicationAuthor.publication_id.in_([p.id for p in pubs]), PublicationAuthor.is_applicant.is_(False))
    )) if pubs else []
    reported = s.scalar(select(ScopusEvidence).where(ScopusEvidence.case_id == case_id))
    applicant = rules.ApplicantSide(
        coauthor_name_keys=frozenset(k for k in (rules.name_key(n) for n in names) if k),
        institution_ids=frozenset([config.INSTITUTION_OPENALEX_ID] if config.INSTITUTION_OPENALEX_ID else []),
        institution_names=frozenset({config.INSTITUTION_NAME}),
        h_index=reported.h_index if reported else None,
        citations=reported.total_citations if reported else None)

    since = now - timedelta(days=365 * rules.REUSE_YEARS + 1)
    used = s.scalars(select(Referee.openalex_author_id).join(ReviewerAssignment,
                                                             ReviewerAssignment.referee_id == Referee.id)
                     .where(ReviewerAssignment.invited_at >= since, Referee.openalex_author_id.is_not(None)))
    terms = [t for t in [case.specialization, case.fine_specialization, *(case.research_keywords or [])] if t]
    return ShortlistContext(
        case_id=case_id, track=case.track.value, topic_terms=terms, paper_titles=[p.title for p in pubs],
        applicant_ref=case.openalex_author_id or case.orcid, applicant=applicant, recently_used=set(used),
        min_reports=crit.min_referee_reports if crit else 3)


# search, rules, ranking --------------------------------------------------------------------------------

def _candidate(p: scholarly.AuthorProfile) -> rules.Candidate:
    return rules.Candidate(
        key=p.external_id, name=p.name, country=p.country,
        institution_ids=frozenset(i["id"] for i in p.institutions if i.get("id")),
        institution_names=frozenset(i["name"] for i in p.institutions if i.get("name")),
        h_index=p.h_index, citations=p.citations, works=p.works, topics=tuple(p.topics))


def applicant_profile(ctx: ShortlistContext, now: datetime, get=scholarly.get_json) -> list[FlagOut]:
    """Complete the applicant's side from OpenAlex: verified metrics, institutions and co-authors. If the lookup
    fails, the dossier's author lists and self-reported metrics are used, and a flag says so."""
    if not ctx.applicant_ref:
        return [FlagOut(severity=FlagSeverity.WARNING, code="applicant_not_on_openalex",
                        message="Section 0 has no OpenAlex id or ORCID: co-authorship conflicts were checked against "
                                "the dossier's author lists only.")]
    try:
        prof = scholarly.openalex_author(ctx.applicant_ref, get)
        coauthors = scholarly.openalex_coauthor_ids(prof.external_id, now.year - COAUTHOR_YEARS, get)
    except (scholarly.Unavailable, scholarly.NoAccess, scholarly.NotFound) as e:
        return [FlagOut(severity=FlagSeverity.WARNING, code="applicant_profile_unavailable",
                        message=f"The applicant's OpenAlex profile could not be read ({type(e).__name__}): "
                                "co-authorship conflicts were checked against the dossier's author lists only.")]
    a = ctx.applicant
    ctx.applicant_ref = prof.external_id
    ctx.applicant = rules.ApplicantSide(
        coauthor_ids=frozenset(coauthors), coauthor_name_keys=a.coauthor_name_keys,
        institution_ids=a.institution_ids | {i["id"] for i in prof.institutions if i.get("id")},
        institution_names=a.institution_names | {i["name"] for i in prof.institutions if i.get("name")},
        h_index=prof.h_index if prof.h_index is not None else a.h_index,
        citations=prof.citations if prof.citations is not None else a.citations)
    return []


def search(ctx: ShortlistContext, now: datetime, get=scholarly.get_json) -> list[scholarly.AuthorProfile]:
    """OpenAlex authors active on the topic in the last 5 years, with their profiles."""
    query = " ".join(ctx.topic_terms[:6]) or " ".join(ctx.paper_titles[:2])
    if not query:
        return []
    exclude = {ctx.applicant_ref} if ctx.applicant_ref else set()
    ids = scholarly.openalex_candidate_ids(query, now.year - SEARCH_YEARS, exclude, SEARCH_POOL, get)
    return scholarly.openalex_authors(ids, get)


def _reason_group(reason: str) -> str:
    """Group the rule's reasons for the summary flag."""
    for word, group in (("co-authored", "co-author"), ("institution", "same institution"),
                        ("5 years", "used in the last 5 years"), ("UAE", "inside the UAE / unknown country"),
                        ("country", "inside the UAE / unknown country"), ("h-index", "metrics below the applicant's"),
                        ("citations", "metrics below the applicant's")):
        if word in reason:
            return group
    return reason


@dataclass
class Plan:
    """What the agent decided, before anything is saved."""
    ranked: list[tuple[scholarly.AuthorProfile, float, str, DecisionBasis]] = field(default_factory=list)
    flags: list[FlagOut] = field(default_factory=list)
    model_name: str | None = None
    searched: int = 0


def plan(ctx: ShortlistContext, found: list[scholarly.AuthorProfile], llm) -> Plan:
    out = Plan(searched=len(found))
    eligible: list[scholarly.AuthorProfile] = []
    removed: dict[str, int] = {}
    for p in found:
        c = _candidate(p)
        ok, reasons = rules.eligibility(c, ctx.applicant, rules.conflicts(c, ctx.applicant, ctx.recently_used))
        if ok:
            eligible.append(p)
        for key in {_reason_group(r) for r in reasons}:
            removed[key] = removed.get(key, 0) + 1
    if removed:
        out.flags.append(FlagOut(severity=FlagSeverity.INFO, code="candidates_removed",
                                 message=f"{len(found) - len(eligible)} of {len(found)} candidates were removed by "
                                         "the conflict-of-interest and eligibility rules: "
                                         + "; ".join(f"{k} ({n})" for k, n in sorted(removed.items())) + "."))

    handles = {f"c-{i + 1}": p for i, p in enumerate(eligible)}
    scores: dict[str, tuple[float, str, DecisionBasis]] = {}
    if eligible and llm is not None:
        payload = {"applicant": {"field_terms": ctx.topic_terms, "paper_titles": ctx.paper_titles[:15]},
                   "candidates": [{"handle": h, "topics": p.topics[:10], "h_index": p.h_index,
                                   "citations": p.citations, "works": p.works} for h, p in handles.items()]}
        messages = [("system", SYSTEM), ("human", json.dumps(payload, ensure_ascii=False))]
        for _attempt in (1, 2):
            try:
                result = llm.with_structured_output(Ranking).invoke(messages)
            except Exception as e:
                     out.flags.append(FlagOut(severity=FlagSeverity.INFO, code="llm_unavailable",
                             message=f"The language model failed ({type(e).__name__}); the candidates "
                                        "were not ranked by field alignment."))
                break
            for r in result.items:
                h = r.handle.strip().lower()
                if h in handles:
                    scores[h] = (min(max(r.score, 0.0), 1.0), r.rationale[:400], DecisionBasis.LLM)
            missing = [h for h in handles if h not in scores]
            if not missing:
                out.model_name = llm_module.model_name()
                break
            messages = messages[:2] + [("human", "You did not score these handles: " + ", ".join(missing)
                                        + ". Return every candidate.")]
        if scores and out.model_name is None:
            out.model_name = llm_module.model_name()
    elif eligible:
        out.flags.append(FlagOut(severity=FlagSeverity.INFO, code="llm_unavailable",
                                 message="No language model is configured; candidates were ranked by topic-word "
                                         "overlap instead."))
    unranked = [h for h in handles if h not in scores]
    for h in unranked:                       # the model did not rank them: no guess, a person ranks them
        scores[h] = (0.0, "Not ranked: the language model was unavailable.", DecisionBasis.RULE)
    if unranked:
        out.flags.append(FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="ranking_not_done",
                                 message=f"{len(unranked)} candidate(s) were not ranked by field alignment because the "
                                         "language model was unavailable. Rank them manually or run the agent again."))
    ordered = sorted(handles, key=lambda h: (-scores[h][0], -(handles[h].h_index or 0), handles[h].external_id))
    out.ranked = [(handles[h], *scores[h]) for h in ordered[:rules.MAX_SHORTLIST]]

    if len(out.ranked) < ctx.min_reports:
        out.flags.append(FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="too_few_candidates",
                                 message=f"Only {len(out.ranked)} eligible candidate(s) found; at least "
                                         f"{ctx.min_reports} referee reports are needed. Add candidates manually."))
    if out.ranked:
        out.flags.append(FlagOut(severity=FlagSeverity.WARNING, code="rank_and_email_to_confirm",
                                 message="OpenAlex does not record academic rank or email. Before contacting a "
                                         "referee, confirm that they are a Full Professor and enter their email."))
    return out


#--save
def save(s: Session, ctx: ShortlistContext, p: Plan) -> tuple[list[dict], AgentOutput]:
    # A re-run replaces the previous suggestions, but never a candidate the Chancellor already selected.
    s.execute(delete(RefereeCandidate).where(RefereeCandidate.case_id == ctx.case_id,
                                             RefereeCandidate.selected_by_chancellor.is_(False)))
    shortlist, items = [], []
    for prof, score, rationale, basis in p.ranked:
        ref = s.scalar(select(Referee).where(Referee.openalex_author_id == prof.external_id))
        if ref is None:
            ref = Referee(openalex_author_id=prof.external_id, rank=None)
            s.add(ref)
        ref.full_name = prof.name or prof.external_id
        ref.university = (prof.institutions[0]["name"] if prof.institutions else None) or "Unknown"
        ref.country_code = (prof.country or "").upper()[:2]
        ref.h_index, ref.citation_count, ref.topics = prof.h_index, prof.citations, prof.topics
        s.flush()
        cand = s.scalar(select(RefereeCandidate).where(RefereeCandidate.case_id == ctx.case_id,
                                                       RefereeCandidate.referee_id == ref.id))
        if cand is None:
            cand = RefereeCandidate(case_id=ctx.case_id, referee_id=ref.id)
            s.add(cand)
        cand.match_score = Decimal(str(round(score, 3)))
        cand.match_rationale = rationale
        cand.coi_coauthor = cand.coi_same_institution = cand.coi_used_within_5_years = False
        cand.eligible = True
        s.flush()
        shortlist.append({"candidate_id": cand.id, "referee_id": ref.id, "coi_clear": True, "eligible": True,
                          "match_score": float(cand.match_score), "rank_confirmed": ref.rank is not None})
        items.append(ItemOut(entity_table="referee_candidate", entity_id=cand.id, counted=True,
                             classification=f"match {float(cand.match_score):.2f}", basis=basis,
                             confidence=Confidence.MEDIUM, reason=rationale))
    verdict = Verdict.NEEDS_HUMAN if any(f.severity == FlagSeverity.NEEDS_HUMAN for f in p.flags) else Verdict.PASS
    out = AgentOutput(component=Component.CHANCELLOR_OFFICE, verdict=verdict, items=items, flags=p.flags,
                      narrative=f"{p.searched} researchers found on the applicant's topic in the last "
                                f"{SEARCH_YEARS} years; {len(shortlist)} conflict-free, eligible candidate(s) "
                                "shortlisted for the Chancellor's selection.",
                      confidence=Confidence.MEDIUM, model_name=p.model_name, prompt_version=PROMPT_VERSION)
    save_output(s, ctx.case_id, out)
    return shortlist, out


def run(state: CaseState) -> dict:
    if use_stubs(state):        # tests and demos of the graph's flow only
        return {"shortlist": [{"candidate_id": i, "coi_clear": True} for i in range(1, 4)]}
    case_id = state["case_id"]
    now = datetime.now(timezone.utc)
    with db_session.session_scope() as s:
        ctx = build_context(s, case_id, now)
    profile_flags = applicant_profile(ctx, now)
    try:
        found = search(ctx, now)
        search_error = None
    except (scholarly.Unavailable, scholarly.NoAccess, scholarly.NotFound) as e:
        found, search_error = [], f"{type(e).__name__}: {e}"
    try:
        llm = llm_module.get_llm()
    except llm_module.LLMNotConfigured:
        llm = None
    p = plan(ctx, found, llm)
    p.flags = profile_flags + p.flags
    if search_error:
        p.flags.append(FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="referee_search_failed",
                               message=f"The OpenAlex search failed ({search_error}). Run the agent again later or "
                                       "add candidates manually."))
    with db_session.session_scope() as s:
        shortlist, _ = save(s, ctx, p)
    return {"shortlist": shortlist}

