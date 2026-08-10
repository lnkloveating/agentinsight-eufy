"""Persist universal recovery submission field bindings.

Revision ID: 0018_universal_agent_recovery
Revises: 0017_product_gap_recovery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_universal_agent_recovery"
down_revision: str | None = "0017_product_gap_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_recovery_submissions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "submission_kind",
                sa.String(length=30),
                nullable=False,
                server_default="direct_answer",
            )
        )
        batch_op.add_column(
            sa.Column(
                "field_ids_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("source_recovery_submissions") as batch_op:
        batch_op.drop_column("field_ids_json")
        batch_op.drop_column("submission_kind")
