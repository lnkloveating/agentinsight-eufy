"""Add auditable Source Fragment to Evidence review batches.

Revision ID: 0015_fragment_evidence_pipeline
Revises: 0014_competitor_material_discovery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_fragment_evidence_pipeline"
down_revision: str | None = "0014_competitor_material_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fragment_evidence_batches",
        sa.Column("fragment_evidence_batch_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_asset_ids_json", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("fragment_evidence_decision_id", sa.String(length=40), nullable=True),
        sa.Column("decision_action", sa.String(length=20), nullable=True),
        sa.Column("selected_item_ids_json", sa.JSON(), nullable=False),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("fragment_evidence_batch_id"),
        sa.UniqueConstraint("fragment_evidence_decision_id"),
    )
    op.create_index(
        "ix_fragment_evidence_batches_project_created",
        "fragment_evidence_batches",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_fragment_evidence_batches_project_id",
        "fragment_evidence_batches",
        ["project_id"],
    )
    op.create_index(
        "ix_fragment_evidence_batches_status",
        "fragment_evidence_batches",
        ["status"],
    )

    op.create_table(
        "fragment_evidence_batch_items",
        sa.Column("fragment_evidence_item_id", sa.String(length=40), nullable=False),
        sa.Column("fragment_evidence_batch_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("source_fragment_id", sa.String(length=40), nullable=False),
        sa.Column("eligibility", sa.String(length=30), nullable=False),
        sa.Column("block_reasons_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_routes_json", sa.JSON(), nullable=False),
        sa.Column("allowed_claim_types_json", sa.JSON(), nullable=False),
        sa.Column("suggested_claim_type", sa.String(length=40), nullable=True),
        sa.Column("product_role", sa.String(length=20), nullable=True),
        sa.Column("product_json", sa.JSON(), nullable=True),
        sa.Column("dimensions_json", sa.JSON(), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("authority_score", sa.Float(), nullable=False),
        sa.Column("recency_score", sa.Float(), nullable=False),
        sa.Column("diversity_score", sa.Float(), nullable=False),
        sa.Column("quality_reasons_json", sa.JSON(), nullable=False),
        sa.Column("existing_evidence_id", sa.String(length=40), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("selected_claim_type", sa.String(length=40), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_segment", sa.String(length=160), nullable=True),
        sa.Column("promotion_status", sa.String(length=30), nullable=False),
        sa.Column("evidence_id", sa.String(length=40), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["fragment_evidence_batch_id"],
            ["fragment_evidence_batches.fragment_evidence_batch_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["source_assets.source_asset_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_fragment_id"], ["source_fragments.source_fragment_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.evidence_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("fragment_evidence_item_id"),
        sa.UniqueConstraint(
            "fragment_evidence_batch_id",
            "source_fragment_id",
            name="uq_fragment_evidence_batch_fragment",
        ),
    )
    op.create_index(
        "ix_fragment_evidence_batch_items_project_fragment",
        "fragment_evidence_batch_items",
        ["project_id", "source_fragment_id"],
    )
    for column in (
        "fragment_evidence_batch_id",
        "project_id",
        "source_asset_id",
        "source_fragment_id",
        "evidence_id",
    ):
        op.create_index(
            f"ix_fragment_evidence_batch_items_{column}",
            "fragment_evidence_batch_items",
            [column],
        )


def downgrade() -> None:
    op.drop_table("fragment_evidence_batch_items")
    op.drop_table("fragment_evidence_batches")
