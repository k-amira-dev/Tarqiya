"""What the reviewer's report shows, worked out from an evaluation's result (no Streamlit in here, so it is easy to test).

An evaluation's result (`AgentOutput` saved as a dict) is long and technical. This turns it into the few things a Head of
Department or Dean reads at a glance:
  * a one-line summary for the strip at the top of the report ("28 / 30", "12 of 12 checks", ...)
  * a points table for Teaching and Service (one row per rubric item: points out of the maximum, how it was decided)
  * a checks table for Eligibility (one row per check: required, actual, result)
Reports saved before `max_value` existed still work: the maximum is then simply left out.
"""
from dataclasses import dataclass

# What the reviewer sees instead of the internal names.
TITLE = {"eligibility": "Eligibility check", "research": "Research evaluation", "teaching": "Teaching evaluation",
         "service": "Service evaluation"}
HOW = {"rule": "Rule-based", "llm": "AI-assisted", "mixed": "Rule + AI"}
CONFIDENCE = {"high": "High", "medium": "Medium", "low": "Low"}


@dataclass(frozen=True)
class Summary:
    name: str
    title: str
    verdict: str          # pass | fail | needs_human | incomplete
    figure: str           # the big text on the tile
    detail: str           # the small text under it


@dataclass(frozen=True)
class PointsRow:
    item_no: int
    label: str
    points: float
    max_points: float | None
    share: float | None   # points / max, 0..1 (None when the maximum is unknown)
    how: str              # "Rule-based" | "AI-assisted" | ...
    confidence: str       # "High" | "Medium" | "Low" | ""
    reason: str
    no_evidence: bool
    opinions: tuple = ()  # committee only: ((model, points, reason), ...) in the committee's order
    disagree: bool = False  # the models disagreed on this item and a person should decide


@dataclass(frozen=True)
class PointsTable:
    total: float
    max_total: float | None
    pass_mark: float | None
    passed: bool | None
    rows: list[PointsRow]
    models: tuple = ()    # committee only: the model names, one table column each (empty = a single model)


def short_model(name: str) -> str:
    """openai/gpt-oss-120b -> gpt-oss-120b"""
    return name.split("/")[-1]


@dataclass(frozen=True)
class CheckRow:
    label: str
    required: float | None
    actual: float | None
    passed: bool | None   # None = a person must decide
    policy_ref: str


def g(x: float | None) -> str:
    """12.0 -> "12", 4.5 -> "4.5", None -> "–"."""
    return "–" if x is None else f"{x:g}"


def _total_criterion(out: dict) -> dict | None:
    return next((c for c in out.get("criteria", []) if c["key"].endswith("_total")), None)


def points_table(out: dict) -> PointsTable | None:
    """The Teaching / Service points table, or None for an evaluation that has no rubric lines."""
    lines = out.get("rubric") or []
    if not lines:
        return None
    by_key = {c["key"]: c for c in out.get("criteria", [])}
    total = _total_criterion(out)
    rows = []
    # Items where the committee's models disagreed (the engine flags them "Item N: the models disagree ...").
    disagree = {int(f["message"].split(":", 1)[0].split()[1]) for f in out.get("flags", [])
                if f.get("code") == "committee_disagreement" and f.get("message", "").startswith("Item ")}
    models: list[str] = []
    for ln in sorted(lines, key=lambda x: x["item_no"]):
        crit = by_key.get(f"item_{ln['item_no']}", {})
        label = crit.get("label", f"Item {ln['item_no']}")
        label = label.split(": ", 1)[1] if label.startswith("Item ") and ": " in label else label
        mx = crit.get("max_value")
        pts = float(ln["suggested_points"])
        rows.append(PointsRow(
            item_no=ln["item_no"], label=label, points=pts, max_points=mx,
            share=(pts / mx if mx else None), how=HOW.get(ln.get("basis"), ""),
            confidence=CONFIDENCE.get(ln.get("confidence") or "", ""), reason=ln.get("rationale") or "",
            no_evidence=(ln.get("rationale") or "").startswith("No evidence"),
            opinions=tuple((short_model(o["model_name"]), float(o["points"]), o.get("rationale") or "") for o in ln.get("opinions") or []),
            disagree=ln["item_no"] in disagree))
        models += [m for m, _, _ in rows[-1].opinions if m not in models]
    return PointsTable(total=total["actual"] if total else sum(r.points for r in rows),
                       max_total=total.get("max_value") if total else None,
                       pass_mark=total.get("required") if total else None,
                       passed=total.get("passed") if total else None, rows=rows, models=tuple(models))


def check_rows(out: dict) -> list[CheckRow]:
    """The Eligibility checks, one row each."""
    return [CheckRow(c["label"], c.get("required"), c.get("actual"), c.get("passed"), c.get("policy_ref") or "")
            for c in out.get("criteria", [])]


def summary(name: str, out: dict) -> Summary:
    """The tile for this evaluation at the top of the report."""
    title, verdict = TITLE.get(name, name.title()), out["verdict"]
    if out.get("is_stub"):
        return Summary(name, title, verdict, "Not built yet", "Placeholder result")
    table = points_table(out)
    if table is not None:
        figure = f"{g(table.total)} / {g(table.max_total)}" if table.max_total else g(table.total)
        return Summary(name, title, verdict, figure, f"pass mark {g(table.pass_mark)}")
    checks = check_rows(out)
    if checks:
        ok = sum(1 for c in checks if c.passed is True)
        return Summary(name, title, verdict, f"{ok} of {len(checks)} checks", "conditions met")
    return Summary(name, title, verdict, "–", "")


# ---- Research: one row per paper ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class PaperRow:
    title: str
    journal: str
    journal_class: str          # "Class A", "Class B" or "Not counted" (decided by rule from the journal table)
    declared: bool              # the journal's class comes from the applicant's own classification form, not an official ranking
    counted: bool | None
    credited: str               # "Main author", "Co-author" ...
    topic: str                  # "Fits the field (AI)", "Check: <reason>", or "Not checked"
    topic_ok: bool | None


CLASS_NAME = {"class_a": "Class A", "class_b": "Class B", "not_counted": "Not counted"}


def paper_rows(out: dict, papers: dict[int, tuple[str, str, bool]]) -> list[PaperRow]:
    """One row per paper of a Research report. `papers` maps a publication id to (title, journal name, class declared in the form).

    The class and the counting are the rules' decision. The topic check is the language model's: it judges every paper and the
    report keeps only the papers it found OUTSIDE the field (as a warning), so a paper with no warning was judged relevant,
    unless the model did not run (then it says "Not checked")."""
    model_ran = bool(out.get("model_name")) and not any(f.get("code") == "llm_unavailable" for f in out.get("flags", []))
    mismatch = {f.get("entity_id"): f.get("message", "") for f in out.get("flags", []) if f.get("code") == "topic_mismatch"}
    rows = []
    for it in out.get("items", []):
        if it.get("entity_table") != "publication" or it["entity_id"] not in papers:
            continue
        title, journal, declared = papers[it["entity_id"]]
        pid = it["entity_id"]
        if pid in mismatch:
            topic, ok = "Check: " + mismatch[pid].split("): ", 1)[-1].replace(" A reviewer should check.", ""), False
        elif model_ran:
            topic, ok = "Fits the field (AI)", True
        else:
            topic, ok = "Not checked", None
        rows.append(PaperRow(title, journal, CLASS_NAME.get(it.get("classification"), it.get("classification") or ""), declared, it.get("counted"),
                             (it.get("credited_role") or "").capitalize(), topic, ok))
    return rows
