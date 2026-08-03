"""创建项目生命周期表。

Revision ID: 0001_project_lifecycle
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_project_lifecycle"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("current_stage", sa.String(length=80), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("brief_json", sa.JSON(), nullable=False),
        sa.Column("pending_decision_json", sa.JSON(), nullable=True),
        sa.Column("checkpoint_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index("ix_projects_status", "projects", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("agent_run_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("agent_type", sa.String(length=80), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_run_id"),
    )
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_project_status", "agent_runs", ["project_id", "status"])

    op.create_table(
        "project_events",
        sa.Column("event_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("project_id", "sequence_number", name="uq_project_event_sequence"),
    )
    op.create_index("ix_project_events_project_id", "project_events", ["project_id"])
    op.create_index("ix_project_events_event_type", "project_events", ["event_type"])
    op.create_index("ix_project_events_trace_id", "project_events", ["trace_id"])
    op.create_index(
        "ix_project_events_project_created", "project_events", ["project_id", "created_at"]
    )

    op.create_table(
        "decisions",
        sa.Column("decision_record_id", sa.String(length=40), nullable=False),
        sa.Column("decision_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("gate", sa.String(length=30), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("selected_concept_ids_json", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_record_id"),
    )
    op.create_index("ix_decisions_decision_id", "decisions", ["decision_id"])
    op.create_index("ix_decisions_project_id", "decisions", ["project_id"])
    op.create_index("ix_decisions_project_created", "decisions", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_table("decisions")
    op.drop_table("project_events")
    op.drop_table("agent_runs")
    op.drop_table("projects")
