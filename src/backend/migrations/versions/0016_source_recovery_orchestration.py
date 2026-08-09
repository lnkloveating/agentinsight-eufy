"""Add auditable source recovery orchestration.

Revision ID: 0016_source_recovery_orchestration
Revises: 0015_fragment_evidence_pipeline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_source_recovery_orchestration"
down_revision: str | None = "0015_fragment_evidence_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_recoveries",
        sa.Column("source_recovery_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("failed_source_asset_id", sa.String(length=40), nullable=True),
        sa.Column("failed_collection_job_id", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("reason_message", sa.Text(), nullable=False),
        sa.Column("requirement_ids_json", sa.JSON(), nullable=False),
        sa.Column("requested_fields_json", sa.JSON(), nullable=False),
        sa.Column("affected_task_ids_json", sa.JSON(), nullable=False),
        sa.Column("affected_agent_types_json", sa.JSON(), nullable=False),
        sa.Column("assessment_before_json", sa.JSON(), nullable=False),
        sa.Column("current_assessment_json", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("request_reason", sa.Text(), nullable=False),
        sa.Column("decision_actor", sa.String(length=120), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["failed_source_asset_id"], ["source_assets.source_asset_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["failed_collection_job_id"],
            ["collection_jobs.collection_job_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("source_recovery_id"),
    )
    op.create_index(
        "ix_source_recoveries_project_status",
        "source_recoveries",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_source_recoveries_project_source",
        "source_recoveries",
        ["project_id", "failed_source_asset_id"],
    )
    for column in (
        "project_id",
        "failed_source_asset_id",
        "failed_collection_job_id",
        "status",
        "trace_id",
    ):
        op.create_index(f"ix_source_recoveries_{column}", "source_recoveries", [column])

    op.create_table(
        "source_recovery_submissions",
        sa.Column("submission_id", sa.String(length=40), nullable=False),
        sa.Column("source_recovery_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("source_asset_id", sa.String(length=40), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("answer_count", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_recovery_id"], ["source_recoveries.source_recovery_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_asset_id"], ["source_assets.source_asset_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("submission_id"),
        sa.UniqueConstraint(
            "source_recovery_id",
            "request_id",
            name="uq_source_recovery_submission_request",
        ),
    )
    op.create_index(
        "ix_source_recovery_submissions_project_created",
        "source_recovery_submissions",
        ["project_id", "created_at"],
    )
    for column in ("source_recovery_id", "project_id", "source_asset_id"):
        op.create_index(
            f"ix_source_recovery_submissions_{column}",
            "source_recovery_submissions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("source_recovery_submissions")
    op.drop_table("source_recoveries")
