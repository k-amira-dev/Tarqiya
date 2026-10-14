"""Small helper commands for the workflow. Run one of:

    .venv\\Scripts\\python -m promoflow.workflow.tools demo       walk three cases through the stub graph (no database)
    .venv\\Scripts\\python -m promoflow.workflow.tools draw       draw the graph to docs/workflow_graph.mmd (+ .png if online)
    .venv\\Scripts\\python -m promoflow.workflow.tools setup-db   one time: create LangGraph's checkpoint tables
    .venv\\Scripts\\python -m promoflow.workflow.tools review-demo   DEV ONLY: send the test applicant's case to the HoD

None of this is used by the website itself. It is a toolbox for developers: handy for seeing the flow work, drawing
the picture of the graph, and preparing a demo."""
import argparse
from pathlib import Path

from langgraph.types import Command

from promoflow.workflow.graph import build_graph, memory_checkpointer, postgres_checkpointer


def _show(graph, payload, config) -> None:
    """Run (or continue) the graph and print each step as it happens.

    stream_mode="updates" yields one item per node that finished. A pause at a human gate shows up under the special
    key "__interrupt__"."""
    for update in graph.stream(payload, config, stream_mode="updates"):
        for node, value in update.items():
            if node == "__interrupt__":
                print(f"   PAUSED, waiting for: {value[0].value['gate'].upper()}")
            else:
                print(f"   ran: {node}")


def demo() -> None:
    """Walk three fake cases through the graph in memory (no database, no language model)."""
    graph = build_graph(memory_checkpointer())

    # Each case has its own thread_id, which is how LangGraph keeps separate runs apart.
    print("Case 1: eligible, approved by HoD and Dean, Chancellor picks referees")
    cfg = {"configurable": {"thread_id": "case-1"}}
    _show(graph, {"case_id": 1, "options": {"stub_eligible": True}}, cfg)
    # After each pause we continue the run with Command(resume=...), which is what review_service.resume() does too.
    _show(graph, Command(resume={"outcome": "approve", "comment": "ok"}), cfg)       # HoD
    _show(graph, Command(resume={"outcome": "approve", "comment": "ok"}), cfg)       # Dean
    _show(graph, Command(resume={"selected": [1, 2]}), cfg)                          # Chancellor
    print("   final:", graph.get_state(cfg).values["final_status"])

    print("\nCase 2: not eligible")
    cfg = {"configurable": {"thread_id": "case-2"}}
    _show(graph, {"case_id": 2, "options": {"stub_eligible": False}}, cfg)
    print("   final:", graph.get_state(cfg).values["final_status"])

    print("\nCase 3: HoD returns it for revision")
    cfg = {"configurable": {"thread_id": "case-3"}}
    _show(graph, {"case_id": 3, "options": {"stub_eligible": True}}, cfg)
    _show(graph, Command(resume={"outcome": "return_for_revision", "sections": ["5"], "comment": "fix 5A"}), cfg)
    print("   final:", graph.get_state(cfg).values["final_status"])


def draw() -> None:
    """Save a picture of the graph, to compare with System architecture.png."""
    out = Path("docs")
    out.mkdir(exist_ok=True)
    drawable = build_graph().get_graph()
    (out / "workflow_graph.mmd").write_text(drawable.draw_mermaid(), encoding="utf-8")   # the diagram as text
    print("Wrote docs/workflow_graph.mmd")
    try:
        (out / "workflow_graph.png").write_bytes(drawable.draw_mermaid_png())   # renders through mermaid.ink
        print("Wrote docs/workflow_graph.png")
    except Exception as e:
        print("Could not make the PNG (needs internet):", e)
        print("Paste the .mmd text into https://mermaid.live to see the picture.")


def setup_db() -> None:
    """Create the tables LangGraph needs to save paused runs. Run once per database."""
    postgres_checkpointer().setup()
    print("Checkpoint tables are ready.")


def review_demo(email: str) -> None:
    """DEVELOPMENT ONLY. Puts the test applicant's case into 'submitted' (skipping the submission-window rule and the
    completeness check) and runs it through the graph with placeholder eligibility, so the HoD and Dean pages have
    something to show. Real submissions go through Section 11."""
    # Imported inside the function: this command is rarely used, and the other commands should start fast.
    from datetime import date, datetime, timezone

    from sqlalchemy import select

    from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
    from promoflow.db.models import CaseStatusHistory, User
    from promoflow.db.session import session_scope
    from promoflow.dossier import section0 as s0
    from promoflow.workflow import review_service

    # Realistic Section 0 answers, used only if the account has no case yet.
    sample = {
        "academic_year": "2026/2027", "track": PromotionTrack.TO_ASSOCIATE, "specialization": "Computer Science",
        "fine_specialization": "Machine Learning", "research_keywords": [], "appointment_date": date(2019, 9, 1),
        "rank_on_appointment": Rank.ASSISTANT_PROFESSOR, "current_rank_date": date(2019, 9, 1),
        "scopus_author_id": "57193456789", "orcid": None, "phd_outside_uae": False, "early_application": False,
        "exceptional_case": False, "exceptional_justification": None, "previously_rejected": False,
        "rejection_date": None,
    }
    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit(f"No account with {email}.")
        case = s0.active_case(s, user.id)
        case_id = s0.save(s, user.id, sample, date.today()) if case is None else case.id
        case = s0.active_case(s, user.id)
        if case.status == CaseStatus.DRAFT:
            # Do by hand what Section 11's Submit button does, but without its checks.
            s.add(CaseStatusHistory(case_id=case_id, from_status=case.status, to_status=CaseStatus.SUBMITTED,
                                    changed_by=user.id, note="Submitted by review-demo (dev only)"))
            case.status, case.submitted_at = CaseStatus.SUBMITTED, datetime.now(timezone.utc)
        elif case.status != CaseStatus.SUBMITTED:
            raise SystemExit(f"The case is '{case.status.value}', so there is nothing to start.")
    review_service.start_review(case_id, options={"stub_eligible": True}, wait=True)
    print(f"Case {case_id} is now: {review_service.get_status(case_id).case_status.value}. "
          "Log in as hod.cs@promoflow.test and open Reviews.")


COMMANDS = {"demo": demo, "draw": draw, "setup-db": setup_db}

# This block only runs when the file is started as a program (python -m promoflow.workflow.tools ...), not when
# another file imports it.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=[*COMMANDS, "review-demo"])
    parser.add_argument("--email", default="applicant@promoflow.test", help="review-demo: whose case to use")
    args = parser.parse_args()
    review_demo(args.email) if args.command == "review-demo" else COMMANDS[args.command]()
