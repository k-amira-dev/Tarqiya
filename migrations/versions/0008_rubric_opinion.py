"""Add rubric_opinion: every committee model's own score for a Teaching or Service line.

rubric_score keeps the suggestion (the median of the models). This table keeps each model's points and reason, so the Head
of Department and the Dean can see the opinions and where the models disagreed. It stays empty when only one model is used.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rubric_opinion",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("rubric_score_id", sa.BigInteger(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("points", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["rubric_score_id"], ["rubric_score.id"],
                                name=op.f("fk_rubric_opinion_rubric_score_id_rubric_score"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_opinion")),
        sa.UniqueConstraint("rubric_score_id", "model_name", name=op.f("uq_rubric_opinion_rubric_score_id_model_name")),
    )
    op.create_index(op.f("ix_rubric_opinion_rubric_score_id"), "rubric_opinion", ["rubric_score_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_rubric_opinion_rubric_score_id"), table_name="rubric_opinion")
    op.drop_table("rubric_opinion")
