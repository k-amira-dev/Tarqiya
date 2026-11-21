"""Widen criterion_result.policy_ref from 60 to 200 characters.

The Research evaluation quotes the policy clause in full, for example "Promotion conditions: research minimums
(produced at this university)", which is longer than 60 characters; saving its report failed with
"value too long for type character varying(60)".

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("criterion_result", "policy_ref", existing_type=sa.String(length=60), type_=sa.String(length=200),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column("criterion_result", "policy_ref", existing_type=sa.String(length=200), type_=sa.String(length=60),
                    existing_nullable=True)
