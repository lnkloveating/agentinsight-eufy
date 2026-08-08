"""Add auditable search discovery runs.

Revision ID: 0011_search_discovery
Revises: 0010_source_requirement_scope
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_search_discovery"
down_revision: str | None = "0010_source_requirement_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_discovery_runs",
        sa.Column("search_discovery_run_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("include_domains_json", sa.JSON(), nullable=False),
        sa.Column("exclude_domains_json", sa.JSON(), nullable=False),
        sa.Column("candidates_json", sa.JSON(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("provider_request_id", sa.String(length=160), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("search_discovery_run_id"),
    )
    op.create_index(
        "ix_search_discovery_runs_project_created",
        "search_discovery_runs",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_search_discovery_runs_project_status",
        "search_discovery_runs",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_search_discovery_runs_project_id",
        "search_discovery_runs",
        ["project_id"],
    )
    op.create_index(
        "ix_search_discovery_runs_provider_id",
        "search_discovery_runs",
        ["provider_id"],
    )
    op.create_index(
        "ix_search_discovery_runs_status",
        "search_discovery_runs",
        ["status"],
    )
    op.create_index(
        "ix_search_discovery_runs_trace_id",
        "search_discovery_runs",
        ["trace_id"],
    )


def downgrade() -> None:
    op.drop_table("search_discovery_runs")
