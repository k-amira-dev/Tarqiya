"""Tamper evidence: hash columns on the audit log and a seal on each model's score.

Only ADDS nullable columns; no data is changed or removed. The columns are filled by the app as rows are saved. Rows written
before this migration are sealed once with:  python -m promoflow.db.seal backfill   (needs AUDIT_HMAC_KEY in .env)

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log_entry", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_log_entry", sa.Column("entry_hash", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_audit_log_entry_entry_hash"), "audit_log_entry", ["entry_hash"], unique=False)
    op.add_column("rubric_opinion", sa.Column("seal", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("rubric_opinion", "seal")
    op.drop_index(op.f("ix_audit_log_entry_entry_hash"), table_name="audit_log_entry")
    op.drop_column("audit_log_entry", "entry_hash")
    op.drop_column("audit_log_entry", "prev_hash")
