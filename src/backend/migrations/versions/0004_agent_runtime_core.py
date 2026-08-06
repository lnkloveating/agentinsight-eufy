"""扩展 Agent Run 并建立版本化 Artifact Store。

Revision ID: 0004_agent_runtime_core
Revises: 0003_innovation_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_agent_runtime_core"
down_revision: str | None = "0003_innovation_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("adapter_type", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("workspace_key", sa.String(length=240), nullable=True))
        batch_op.add_column(sa.Column("trace_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("timeout_seconds", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "input_artifact_ids_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(sa.Column("output_artifact_id", sa.String(length=40), nullable=True))
        batch_op.add_column(
            sa.Column("quality_score", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "evidence_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            )
        )
        batch_op.add_column(
            sa.Column(
                "unknowns_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            )
        )
        batch_op.add_column(
            sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_agent_runs_task_id", ["task_id"])
        batch_op.create_index("ix_agent_runs_trace_id", ["trace_id"])

    op.create_table(
        "agent_artifacts",
        sa.Column("artifact_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("agent_run_id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=80), nullable=False),
        sa.Column("artifact_type", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("contradictions_json", sa.JSON(), nullable=False),
        sa.Column("unknowns_json", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("input_artifact_ids_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.agent_run_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("artifact_id"),
        sa.UniqueConstraint(
            "project_id",
            "task_id",
            "artifact_type",
            "version",
            name="uq_agent_artifact_version",
        ),
    )
    op.create_index("ix_agent_artifacts_project_id", "agent_artifacts", ["project_id"])
    op.create_index("ix_agent_artifacts_agent_run_id", "agent_artifacts", ["agent_run_id"])
    op.create_index("ix_agent_artifacts_task_id", "agent_artifacts", ["task_id"])
    op.create_index("ix_agent_artifacts_artifact_type", "agent_artifacts", ["artifact_type"])
    op.create_index("ix_agent_artifacts_status", "agent_artifacts", ["status"])
    op.create_index(
        "ix_agent_artifacts_project_task", "agent_artifacts", ["project_id", "task_id"]
    )


def downgrade() -> None:
    op.drop_table("agent_artifacts")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_index("ix_agent_runs_trace_id")
        batch_op.drop_index("ix_agent_runs_task_id")
        batch_op.drop_column("cancellation_requested_at")
        batch_op.drop_column("unknowns_json")
        batch_op.drop_column("evidence_ids_json")
        batch_op.drop_column("quality_score")
        batch_op.drop_column("output_artifact_id")
        batch_op.drop_column("input_artifact_ids_json")
        batch_op.drop_column("timeout_seconds")
        batch_op.drop_column("trace_id")
        batch_op.drop_column("workspace_key")
        batch_op.drop_column("attempt_number")
        batch_op.drop_column("adapter_type")
        batch_op.drop_column("task_id")
