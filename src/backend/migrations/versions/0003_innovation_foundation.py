"""建立未来产品候选、评分和红队结果表。

Revision ID: 0003_innovation_foundation
Revises: 0002_evidence_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_innovation_foundation"
down_revision: str | None = "0002_evidence_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "innovations",
        sa.Column("innovation_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("target_user_json", sa.JSON(), nullable=False),
        sa.Column("problem_json", sa.JSON(), nullable=False),
        sa.Column("event_understanding_json", sa.JSON(), nullable=False),
        sa.Column("competitor_gap_ids_json", sa.JSON(), nullable=False),
        sa.Column("technical_assessment_json", sa.JSON(), nullable=False),
        sa.Column("business_assessment_json", sa.JSON(), nullable=False),
        sa.Column("red_team_review_json", sa.JSON(), nullable=True),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("score_breakdown_json", sa.JSON(), nullable=False),
        sa.Column("base_score", sa.Float(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("gate_issues_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("innovation_id"),
    )
    op.create_index("ix_innovations_project_id", "innovations", ["project_id"])
    op.create_index("ix_innovations_status", "innovations", ["status"])
    op.create_index(
        "ix_innovations_project_status", "innovations", ["project_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("innovations")
