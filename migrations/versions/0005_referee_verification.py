"""Database update 0005: a referee is saved with the rank read from ORCID (Full or Associate Professor).
A human proxy must still verify the rank before the Chancellor picks the referee and the invitation is sent, to make sure it is accurate and not outdated.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

# This is update number 5. It runs right after update number 4.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
 
    # A place to keep the referee's ORCID ID (for example 0000-0002-1825-0097), so we can read their
    # job title and email from ORCID.
    op.add_column("referee", sa.Column("orcid", sa.String(19), nullable=True))

    # A yes/no box: has a person checked that this referee's rank is still correct?
    # Every referee starts at "no". Nobody is invited until it is "yes".
    op.add_column("referee", sa.Column("rank_verified", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("referee", "rank_verified")
    op.drop_column("referee", "orcid")
    rank: Mapped[Rank] = mapped_column(pg_enum(Rank))  # from ORCID: Associate or Full Professor; never empty
