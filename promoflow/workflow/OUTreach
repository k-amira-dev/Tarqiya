import argparse
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from email.message import EmailMessage

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow import config
from promoflow.db import session as db_session
from promoflow.db.enums import (
    AssignmentStatus, CaseStatus, DeliveryStatus, FlagSeverity, MessageKind, Rank,
)
from promoflow.db.models import (
    Flag, OutreachMessage, PromotionCase, PromotionCriteria, Referee, RefereeCandidate, RefereePaperGrade,
    RefereeReport, ReviewerAssignment,
)
from promoflow.rules import referees as rules
from promoflow.workflow import llm as llm_module
from promoflow.workflow.nodes import use_stubs
from promoflow.workflow.schemas import CaseState
from promoflow.workflow.verify import handle, parse_handles

WAITING = (AssignmentStatus.INVITED, AssignmentStatus.REMINDED, AssignmentStatus.ACCEPTED)
PLACEHOLDERS = ("{referee_name}", "{deadline}", "{case_ref}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _flag(s: Session, case_id: int, severity: FlagSeverity, code: str, message: str, table=None, eid=None) -> None:
    s.add(Flag(case_id=case_id, severity=severity, code=code, message=message, entity_table=table, entity_id=eid))


# ---- email wording ------------------------------------------------------------------------------------------------

class EmailDraft(BaseModel):
    subject: str
    body: str


TEMPLATES = {
    MessageKind.INVITATION: (
        "Invitation to review a promotion application ({case_ref})",
        "Dear {referee_name},\n\nThe University of Sharjah invites you to act as an external referee for an "
        "application for promotion to {target_rank} in {field}. You would grade the applicant's counted "
        "publications and send a short report.\n\nPlease let us know whether you accept. If you accept, we would "
        "be grateful to receive your report by {deadline}.\n\nWith thanks,\nOffice of the Chancellor"),
    MessageKind.REMINDER: (
        "Reminder: promotion review request ({case_ref})",
        "Dear {referee_name},\n\nThis is a kind reminder of our request to review an application for promotion to "
        "{target_rank} in {field}. We would be grateful for your answer, and for your report by {deadline}.\n\n"
        "With thanks,\nOffice of the Chancellor"),
    MessageKind.REPLACEMENT_NOTICE: (
        "Promotion review request withdrawn ({case_ref})",
        "Dear {referee_name},\n\nAs we have not received a reply, we have withdrawn our request to review the "
        "application ({case_ref}). Thank you for your time; no further action is needed.\n\n"
        "With kind regards,\nOffice of the Chancellor"),
    MessageKind.THANK_YOU: (
        "Thank you for your review ({case_ref})",
        "Dear {referee_name},\n\nThank you for your report on the promotion application ({case_ref}). Your help is "
        "much appreciated.\n\nWith kind regards,\nOffice of the Chancellor"),
}
