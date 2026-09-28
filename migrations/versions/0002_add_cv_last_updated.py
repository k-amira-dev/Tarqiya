"""Add promotion_case.cv_last_updated (spec §2 – Curriculum Vitae).

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promotion_case", sa.Column("cv_last_updated", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("promotion_case", "cv_last_updated")
