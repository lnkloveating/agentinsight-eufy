"""Add auditable competitor A2A specialist tasks.

Revision ID: 0008_competitor_a2a_foundation
Revises: 0007_source_processing_pipeline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_competitor_a2a_foundation"
down_revision: str | None = "0007_source_processing_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "a2a_tasks",
        sa.Column("a2a_task_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("parent_agent_run_id", sa.String(length=40), nullable=False),
        sa.Column("parent_task_id", sa.String(length=80), nullable=False),
        sa.Column("specialist_type", sa.String(length=40), nullable=False),
        sa.Column("adapter_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_agent_run_id"], ["agent_runs.agent_run_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("a2a_task_id"),
        sa.UniqueConstraint(
            "project_id",
            "parent_task_id",
            "specialist_type",
            name="uq_a2a_task_identity",
        ),
    )
    op.create_index("ix_a2a_tasks_project_id", "a2a_tasks", ["project_id"])
    op.create_index(
        "ix_a2a_tasks_parent_agent_run_id", "a2a_tasks", ["parent_agent_run_id"]
    )
    op.create_index("ix_a2a_tasks_parent_task_id", "a2a_tasks", ["parent_task_id"])
    op.create_index("ix_a2a_tasks_status", "a2a_tasks", ["status"])
    op.create_index("ix_a2a_tasks_trace_id", "a2a_tasks", ["trace_id"])
    op.create_index(
        "ix_a2a_tasks_project_status", "a2a_tasks", ["project_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("a2a_tasks")

