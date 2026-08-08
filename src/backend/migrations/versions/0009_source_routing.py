"""Add auditable multi-label source routing.

Revision ID: 0009_source_routing
Revises: 0008_competitor_a2a_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_source_routing"
down_revision: str | None = "0008_competitor_a2a_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_routings",
        sa.Column("source_routing_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("suggestions_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_routes_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_claim_types_json", sa.JSON(), nullable=False),
        sa.Column("rule_signals_json", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("model_call_id", sa.String(length=40), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["source_assets.source_asset_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("source_routing_id"),
        sa.UniqueConstraint("source_asset_id", name="uq_source_routing_source_asset"),
    )
    op.create_index("ix_source_routings_project_id", "source_routings", ["project_id"])
    op.create_index("ix_source_routings_source_asset_id", "source_routings", ["source_asset_id"])
    op.create_index("ix_source_routings_status", "source_routings", ["status"])
    op.create_index(
        "ix_source_routings_project_status",
        "source_routings",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("source_routings")
