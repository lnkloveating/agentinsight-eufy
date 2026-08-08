"""Add competitor candidate gate decisions.

Revision ID: 0012_competitor_candidate_gate
Revises: 0011_search_discovery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_competitor_candidate_gate"
down_revision: str | None = "0011_search_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_candidate_decisions",
        sa.Column("decision_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("artifact_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("selected_proposal_ids_json", sa.JSON(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["agent_artifacts.artifact_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_id"),
        sa.UniqueConstraint("artifact_id", name="uq_competitor_candidate_decision_artifact"),
    )
    op.create_index(
        "ix_competitor_candidate_decisions_project_created",
        "competitor_candidate_decisions",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_competitor_candidate_decisions_project_id",
        "competitor_candidate_decisions",
        ["project_id"],
    )
    op.create_index(
        "ix_competitor_candidate_decisions_artifact_id",
        "competitor_candidate_decisions",
        ["artifact_id"],
    )
    op.create_index(
        "ix_competitor_candidate_decisions_action",
        "competitor_candidate_decisions",
        ["action"],
    )


def downgrade() -> None:
    op.drop_table("competitor_candidate_decisions")
