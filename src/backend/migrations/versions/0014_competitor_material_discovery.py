"""Add competitor material discovery and selection lineage.

Revision ID: 0014_competitor_material_discovery
Revises: 0013_competitor_source_onboarding
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_competitor_material_discovery"
down_revision: str | None = "0013_competitor_source_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_material_discoveries",
        sa.Column("material_discovery_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_id", sa.String(length=80), nullable=False),
        sa.Column("max_results_per_query", sa.Integer(), nullable=False),
        sa.Column("products_json", sa.JSON(), nullable=False),
        sa.Column("dimensions_json", sa.JSON(), nullable=False),
        sa.Column("scope_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("material_discovery_id"),
    )
    op.create_index(
        "ix_competitor_material_discoveries_project_created",
        "competitor_material_discoveries",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_competitor_material_discoveries_project_id",
        "competitor_material_discoveries",
        ["project_id"],
    )
    op.create_index(
        "ix_competitor_material_discoveries_status",
        "competitor_material_discoveries",
        ["status"],
    )

    op.create_table(
        "competitor_material_discovery_items",
        sa.Column("material_discovery_item_id", sa.String(length=40), nullable=False),
        sa.Column("material_discovery_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("search_discovery_run_id", sa.String(length=40), nullable=False),
        sa.Column("product_role", sa.String(length=20), nullable=False),
        sa.Column("product_identity", sa.String(length=500), nullable=False),
        sa.Column("product_json", sa.JSON(), nullable=False),
        sa.Column("dimension", sa.String(length=40), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_discovery_id"],
            ["competitor_material_discoveries.material_discovery_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["search_discovery_run_id"],
            ["search_discovery_runs.search_discovery_run_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("material_discovery_item_id"),
        sa.UniqueConstraint("search_discovery_run_id"),
        sa.UniqueConstraint(
            "material_discovery_id",
            "product_role",
            "product_identity",
            "dimension",
            name="uq_competitor_material_discovery_plan",
        ),
    )
    for column in ("material_discovery_id", "project_id"):
        op.create_index(
            f"ix_competitor_material_discovery_items_{column}",
            "competitor_material_discovery_items",
            [column],
        )

    op.create_table(
        "competitor_material_decisions",
        sa.Column("material_decision_id", sa.String(length=40), nullable=False),
        sa.Column("material_discovery_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("selected_candidate_ids_json", sa.JSON(), nullable=False),
        sa.Column("authorization_basis", sa.String(length=40), nullable=True),
        sa.Column("authorization_confirmed", sa.Boolean(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_discovery_id"],
            ["competitor_material_discoveries.material_discovery_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("material_decision_id"),
        sa.UniqueConstraint(
            "material_discovery_id", name="uq_competitor_material_decision_discovery"
        ),
    )
    for column in ("material_discovery_id", "project_id"):
        op.create_index(
            f"ix_competitor_material_decisions_{column}",
            "competitor_material_decisions",
            [column],
        )

    op.create_table(
        "competitor_material_selections",
        sa.Column("material_selection_id", sa.String(length=40), nullable=False),
        sa.Column("material_decision_id", sa.String(length=40), nullable=False),
        sa.Column("material_discovery_item_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("search_discovery_run_id", sa.String(length=40), nullable=False),
        sa.Column("candidate_id", sa.String(length=40), nullable=False),
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("product_role", sa.String(length=20), nullable=False),
        sa.Column("product_json", sa.JSON(), nullable=False),
        sa.Column("dimension", sa.String(length=40), nullable=False),
        sa.Column("candidate_json", sa.JSON(), nullable=False),
        sa.Column("source_asset_created", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_decision_id"],
            ["competitor_material_decisions.material_decision_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_discovery_item_id"],
            ["competitor_material_discovery_items.material_discovery_item_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["source_assets.source_asset_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("material_selection_id"),
        sa.UniqueConstraint(
            "material_decision_id",
            "candidate_id",
            name="uq_competitor_material_selection_candidate",
        ),
    )
    op.create_index(
        "ix_competitor_material_selections_project_asset",
        "competitor_material_selections",
        ["project_id", "source_asset_id"],
    )
    for column in (
        "material_decision_id",
        "material_discovery_item_id",
        "project_id",
        "candidate_id",
        "source_asset_id",
    ):
        op.create_index(
            f"ix_competitor_material_selections_{column}",
            "competitor_material_selections",
            [column],
        )


def downgrade() -> None:
    op.drop_table("competitor_material_selections")
    op.drop_table("competitor_material_decisions")
    op.drop_table("competitor_material_discovery_items")
    op.drop_table("competitor_material_discoveries")
