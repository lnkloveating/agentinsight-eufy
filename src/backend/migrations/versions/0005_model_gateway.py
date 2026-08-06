"""保存项目模型选择与模型调用审计。

Revision ID: 0005_model_gateway
Revises: 0004_agent_runtime_core
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_model_gateway"
down_revision: str | None = "0004_agent_runtime_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("model_selection_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("model_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("model_provider", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("prompt_key", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(length=40), nullable=True))
        batch_op.add_column(
            sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "estimated_cost_microusd",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_index("ix_agent_runs_model_id", ["model_id"])

    op.create_table(
        "model_calls",
        sa.Column("model_call_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("agent_run_id", sa.String(length=40), nullable=False),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("provider_model", sa.String(length=160), nullable=False),
        sa.Column("prompt_key", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_microusd", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=160), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.agent_run_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model_call_id"),
    )
    op.create_index("ix_model_calls_project_id", "model_calls", ["project_id"])
    op.create_index("ix_model_calls_agent_run_id", "model_calls", ["agent_run_id"])
    op.create_index("ix_model_calls_trace_id", "model_calls", ["trace_id"])
    op.create_index("ix_model_calls_model_id", "model_calls", ["model_id"])
    op.create_index("ix_model_calls_status", "model_calls", ["status"])
    op.create_index(
        "ix_model_calls_project_created", "model_calls", ["project_id", "created_at"]
    )
    op.create_index(
        "ix_model_calls_run_attempt", "model_calls", ["agent_run_id", "attempt_number"]
    )


def downgrade() -> None:
    op.drop_table("model_calls")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_index("ix_agent_runs_model_id")
        batch_op.drop_column("estimated_cost_microusd")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("prompt_key")
        batch_op.drop_column("model_provider")
        batch_op.drop_column("model_id")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("model_selection_json")
