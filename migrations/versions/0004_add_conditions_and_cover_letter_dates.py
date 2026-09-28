"""Add promotion_case.conditions_signed_date and cover_letter_signed_date (spec §9, §10).

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promotion_case", sa.Column("conditions_signed_date", sa.Date(), nullable=True))
    op.add_column("promotion_case", sa.Column("cover_letter_signed_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("promotion_case", "cover_letter_signed_date")
    op.drop_column("promotion_case", "conditions_signed_date")
