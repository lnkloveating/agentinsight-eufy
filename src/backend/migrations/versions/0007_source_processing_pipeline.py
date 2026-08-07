"""Add deterministic parsed artifacts and verified source fragments.

Revision ID: 0007_source_processing_pipeline
Revises: 0006_source_ingestion
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_source_processing_pipeline"
down_revision: str | None = "0006_source_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parsed_artifacts",
        sa.Column("parsed_artifact_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("collection_job_id", sa.String(length=40), nullable=False),
        sa.Column("parser_id", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("fragment_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["source_assets.source_asset_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["collection_job_id"],
            ["collection_jobs.collection_job_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("parsed_artifact_id"),
        sa.UniqueConstraint(
            "collection_job_id", name="uq_parsed_artifact_collection_job"
        ),
    )
    op.create_index("ix_parsed_artifacts_project_id", "parsed_artifacts", ["project_id"])
    op.create_index(
        "ix_parsed_artifacts_source_asset_id", "parsed_artifacts", ["source_asset_id"]
    )
    op.create_index(
        "ix_parsed_artifacts_collection_job_id",
        "parsed_artifacts",
        ["collection_job_id"],
    )
    op.create_index(
        "ix_parsed_artifacts_project_source",
        "parsed_artifacts",
        ["project_id", "source_asset_id"],
    )

    op.create_table(
        "source_fragments",
        sa.Column("source_fragment_id", sa.String(length=40), nullable=False),
        sa.Column("parsed_artifact_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator_json", sa.JSON(), nullable=False),
        sa.Column("original_excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_hash", sa.String(length=64), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parsed_artifact_id"],
            ["parsed_artifacts.parsed_artifact_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["source_assets.source_asset_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("source_fragment_id"),
        sa.UniqueConstraint(
            "parsed_artifact_id",
            "ordinal",
            name="uq_source_fragment_artifact_ordinal",
        ),
    )
    op.create_index(
        "ix_source_fragments_parsed_artifact_id",
        "source_fragments",
        ["parsed_artifact_id"],
    )
    op.create_index("ix_source_fragments_project_id", "source_fragments", ["project_id"])
    op.create_index(
        "ix_source_fragments_source_asset_id", "source_fragments", ["source_asset_id"]
    )
    op.create_index(
        "ix_source_fragments_project_source",
        "source_fragments",
        ["project_id", "source_asset_id"],
    )


def downgrade() -> None:
    op.drop_table("source_fragments")
    op.drop_table("parsed_artifacts")
