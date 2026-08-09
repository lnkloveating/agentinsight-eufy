"""Add competitor source onboarding lineage.

Revision ID: 0013_competitor_source_onboarding
Revises: 0012_competitor_candidate_gate
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_competitor_source_onboarding"
down_revision: str | None = "0012_competitor_candidate_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_source_onboardings",
        sa.Column("onboarding_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("artifact_id", sa.String(length=40), nullable=False),
        sa.Column("decision_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("authorization_basis", sa.String(length=40), nullable=False),
        sa.Column("authorized_by", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["agent_artifacts.artifact_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["competitor_candidate_decisions.decision_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("onboarding_id"),
        sa.UniqueConstraint(
            "artifact_id", name="uq_competitor_source_onboarding_artifact"
        ),
    )
    op.create_index(
        "ix_competitor_source_onboardings_project_created",
        "competitor_source_onboardings",
        ["project_id", "created_at"],
    )
    for column in ("project_id", "artifact_id", "decision_id", "status"):
        op.create_index(
            f"ix_competitor_source_onboardings_{column}",
            "competitor_source_onboardings",
            [column],
        )

    op.create_table(
        "competitor_source_onboarding_items",
        sa.Column("onboarding_item_id", sa.String(length=40), nullable=False),
        sa.Column("onboarding_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("proposal_id", sa.String(length=40), nullable=False),
        sa.Column("candidate_id", sa.String(length=40), nullable=False),
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("product_json", sa.JSON(), nullable=False),
        sa.Column("source_asset_created", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["onboarding_id"],
            ["competitor_source_onboardings.onboarding_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["source_assets.source_asset_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("onboarding_item_id"),
        sa.UniqueConstraint(
            "onboarding_id",
            "candidate_id",
            name="uq_competitor_source_onboarding_candidate",
        ),
    )
    op.create_index(
        "ix_competitor_source_onboarding_items_project_asset",
        "competitor_source_onboarding_items",
        ["project_id", "source_asset_id"],
    )
    for column in (
        "onboarding_id",
        "project_id",
        "proposal_id",
        "candidate_id",
        "source_asset_id",
    ):
        op.create_index(
            f"ix_competitor_source_onboarding_items_{column}",
            "competitor_source_onboarding_items",
            [column],
        )


def downgrade() -> None:
    op.drop_table("competitor_source_onboarding_items")
    op.drop_table("competitor_source_onboardings")
