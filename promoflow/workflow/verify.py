"""verify_claims(): every factual statement an agent makes must point at records that exist in the evidence it was
given. Shared by all LLM agents (spec: one retry, then the claim is marked unverified).

Evidence is shown to the LLM under short "handles" such as `ss-12` (student_satisfaction row 12). Handles, not bare
ids, because ids repeat across tables. Add a prefix here when an agent starts using a new table.

WHY THIS EXISTS (for beginners)
-------------------------------
A language model can "hallucinate": write a confident sentence about something that is not in the data. To catch that,
we never let the model write a free-floating claim. Whenever it justifies a score it must also list the evidence it
used ("cited": ["ss-12", "po-3"]). This file then checks every cited handle really belongs to the evidence we gave it.
A claim that cites nothing, or cites something we never showed the model, is marked unverified and a person is asked
to look."""
import re

from promoflow.workflow.schemas import ClaimOut

# Short code -> database table. Two letters per table keeps the prompts small. Khadidja: add your own tables here
# (for example "pb": "publication") when the Research agent starts citing them.
TABLE_BY_PREFIX = {
    "ct": "course_taught", "ss": "student_satisfaction", "po": "peer_observation",
    "cc": "curriculum_contribution", "ad": "advising_semester", "cf": "course_file",
    "ti": "teaching_innovation", "sv": "supervision", "td": "teaching_development",
    "cm": "committee_membership", "ap": "administrative_position", "pc": "policy_contribution",
    "wk": "workshop_delivered", "tr": "training_delivered", "ca": "community_activity",
    "pb": "publication", "bk": "book", "pt": "patent", "cw": "creative_work", "rc": "referee_candidate",
}
PREFIX_BY_TABLE = {table: prefix for prefix, table in TABLE_BY_PREFIX.items()}   # the same mapping, reversed
# A valid handle is exactly: two lowercase letters, a dash, then digits (e.g. "ss-12").
_HANDLE = re.compile(r"^([a-z]{2})-(\d+)$")


def handle(table: str, record_id: int) -> str:
    """Build the handle for one database row, e.g. handle("student_satisfaction", 12) -> "ss-12"."""
    return f"{PREFIX_BY_TABLE[table]}-{record_id}"


def parse_handles(cited: list[str]) -> tuple[dict[str, list[int]], list[str]]:
    """Group cited handles by table. Returns (table -> ids, handles that are not well formed)."""
    by_table: dict[str, list[int]] = {}
    malformed = []
    for raw in cited:
        m = _HANDLE.match(raw.strip().lower())       # tolerate stray spaces and capital letters from the model
        if not m or m.group(1) not in TABLE_BY_PREFIX:
            malformed.append(raw)
            continue
        by_table.setdefault(TABLE_BY_PREFIX[m.group(1)], []).append(int(m.group(2)))
    return by_table, malformed


def claims_from_citations(text: str, value: float | None, cited: list[str]) -> list[ClaimOut]:
    """One claim per table cited. A statement that cites nothing is still recorded, as an unverifiable claim."""
    by_table, malformed = parse_handles(cited)
    claims = [ClaimOut(text=text, value=value, source_table=table, source_ids=sorted(set(ids)))
              for table, ids in by_table.items()]
    if not claims or malformed:
        # "unresolved" has no records, so verify_claims() will always mark it unverified.
        claims.append(ClaimOut(text=text, value=value, source_table="unresolved", source_ids=[]))
    return claims


def verify_claims(claims: list[ClaimOut], allowed: dict[str, set[int]]) -> list[str]:
    """Mark each claim verified or not, and return a description of every failure (empty = all verified).
    A claim is verified when it cites at least one record and every record it cites is in `allowed`.

    `allowed` is "table name -> the row ids the model was actually shown". It also WRITES the result onto each claim
    (`claim.verified = True/False`), so the caller can save it to the database afterwards."""
    problems = []
    for claim in claims:
        known = allowed.get(claim.source_table, set())
        ok = bool(claim.source_ids) and all(i in known for i in claim.source_ids)
        claim.verified = ok
        if not ok:
            cited = ", ".join(f"{PREFIX_BY_TABLE.get(claim.source_table, '??')}-{i}" for i in claim.source_ids)
            problems.append(f"'{claim.text[:80]}' cites {cited or 'nothing'}, which is not valid evidence for it.")
    return problems
