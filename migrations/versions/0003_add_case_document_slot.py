"""Add case_document.slot, to tell apart several files of the same kind on one entity
(e.g. a degree's "certificate" vs its "equivalency" certificate).

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_document", sa.Column("slot", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("case_document", "slot")
