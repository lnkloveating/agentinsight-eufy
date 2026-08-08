"""Add project source requirement scope.

Revision ID: 0010_source_requirement_scope
Revises: 0009_source_routing
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_source_requirement_scope"
down_revision: str | None = "0009_source_routing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_requirement_scopes",
        sa.Column("source_requirement_scope_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("target_products_json", sa.JSON(), nullable=False),
        sa.Column("competitors_json", sa.JSON(), nullable=False),
        sa.Column("dimensions_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=120), nullable=False),
        sa.Column("update_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_requirement_scope_id"),
        sa.UniqueConstraint("project_id", name="uq_source_requirement_scope_project"),
    )
    op.create_index(
        "ix_source_requirement_scopes_project_id",
        "source_requirement_scopes",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_table("source_requirement_scopes")
