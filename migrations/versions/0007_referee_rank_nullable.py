"""Let referee.rank be empty.

The Chancellor evaluation builds its shortlist from OpenAlex, which does not give an academic rank, so a new referee is saved with no
rank and a person checks the "must be a Professor" rule. The column was NOT NULL, so saving the shortlist failed with
"null value in column rank of relation referee violates not-null constraint" and the case stayed at the Dean gate.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("referee", "rank", nullable=True)


def downgrade() -> None:
    op.alter_column("referee", "rank", nullable=False)
