"""建立用户授权原始资料资产表。

Revision ID: 0006_source_ingestion
Revises: 0005_model_gateway
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_source_ingestion"
down_revision: str | None = "0005_model_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_assets",
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("collection_job_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("normalized_source_url", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("media_type", sa.String(length=160), nullable=False),
        sa.Column("media_category", sa.String(length=30), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("authorization_basis", sa.String(length=40), nullable=False),
        sa.Column("authorization_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorized_by", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_job_id"],
            ["collection_jobs.collection_job_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_asset_id"),
        sa.UniqueConstraint(
            "project_id", "kind", "content_hash", name="uq_source_asset_project_kind_hash"
        ),
        sa.UniqueConstraint("collection_job_id", name="uq_source_asset_collection_job"),
    )
    op.create_index("ix_source_assets_project_id", "source_assets", ["project_id"])
    op.create_index(
        "ix_source_assets_collection_job_id", "source_assets", ["collection_job_id"]
    )
    op.create_index("ix_source_assets_status", "source_assets", ["status"])
    op.create_index(
        "ix_source_assets_project_status", "source_assets", ["project_id", "status"]
    )
    op.create_index(
        "ix_source_assets_project_kind", "source_assets", ["project_id", "kind"]
    )


def downgrade() -> None:
    op.drop_table("source_assets")
