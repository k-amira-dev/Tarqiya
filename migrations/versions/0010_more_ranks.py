"""Two more academic ranks for the rank history (Section 4): Assistant Lecturer and Post-Doctoral Researcher.

Only ADDS two values to the `rank` enum; no data is changed. The promotion rules ignore them (they are not part of the ladder).

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():          # ALTER TYPE ... ADD VALUE cannot run inside a transaction block
        op.execute("ALTER TYPE rank ADD VALUE IF NOT EXISTS 'assistant_lecturer' BEFORE 'lecturer'")
        op.execute("ALTER TYPE rank ADD VALUE IF NOT EXISTS 'postdoc' BEFORE 'lecturer'")


def downgrade() -> None:
    pass                                               # PostgreSQL cannot remove a value from an enum; the extra values are harmless
