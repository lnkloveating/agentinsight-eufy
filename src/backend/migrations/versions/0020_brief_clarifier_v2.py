"""Add persisted pre-project Research Brief clarification sessions.

Revision ID: 0020_brief_clarifier_v2
Revises: 0019_device_capability_graph
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_brief_clarifier_v2"
down_revision: str | None = "0019_device_capability_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brief_clarification_sessions",
        sa.Column("session_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("messages_json", sa.JSON(), nullable=False),
        sa.Column("draft_json", sa.JSON(), nullable=False),
        sa.Column("missing_fields_json", sa.JSON(), nullable=False),
        sa.Column("validation_issues_json", sa.JSON(), nullable=False),
        sa.Column("questions_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_microusd", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        "ix_brief_clarification_sessions_status",
        "brief_clarification_sessions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_brief_clarification_sessions_model_id",
        "brief_clarification_sessions",
        ["model_id"],
        unique=False,
    )
    with op.batch_alter_table("model_calls") as batch_op:
        batch_op.alter_column("project_id", existing_type=sa.String(40), nullable=True)
        batch_op.alter_column("agent_run_id", existing_type=sa.String(40), nullable=True)
        batch_op.add_column(
            sa.Column("clarification_session_id", sa.String(length=40), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_model_calls_clarification_session",
            "brief_clarification_sessions",
            ["clarification_session_id"],
            ["session_id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_model_calls_clarification_session_id",
            ["clarification_session_id"],
            unique=False,
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM model_calls WHERE clarification_session_id IS NOT NULL")
    )
    with op.batch_alter_table("model_calls") as batch_op:
        batch_op.drop_index("ix_model_calls_clarification_session_id")
        batch_op.drop_constraint(
            "fk_model_calls_clarification_session", type_="foreignkey"
        )
        batch_op.drop_column("clarification_session_id")
        batch_op.alter_column("agent_run_id", existing_type=sa.String(40), nullable=False)
        batch_op.alter_column("project_id", existing_type=sa.String(40), nullable=False)
    op.drop_index(
        "ix_brief_clarification_sessions_model_id",
        table_name="brief_clarification_sessions",
    )
    op.drop_index(
        "ix_brief_clarification_sessions_status",
        table_name="brief_clarification_sessions",
    )
    op.drop_table("brief_clarification_sessions")
