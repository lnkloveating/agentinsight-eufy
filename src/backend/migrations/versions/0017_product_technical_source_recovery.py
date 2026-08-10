"""Link Product Technical gaps to Source Recovery.

Revision ID: 0017_product_gap_recovery
Revises: 0016_source_recovery_orchestration
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_product_gap_recovery"
down_revision: str | None = "0016_source_recovery_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_recoveries") as batch_op:
        batch_op.add_column(sa.Column("source_artifact_id", sa.String(length=40), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source_gap_ids_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.create_foreign_key(
            "fk_source_recoveries_source_artifact_id",
            "agent_artifacts",
            ["source_artifact_id"],
            ["artifact_id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_source_recoveries_source_artifact_id",
            ["source_artifact_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("source_recoveries") as batch_op:
        batch_op.drop_index("ix_source_recoveries_source_artifact_id")
        batch_op.drop_constraint(
            "fk_source_recoveries_source_artifact_id", type_="foreignkey"
        )
        batch_op.drop_column("source_gap_ids_json")
        batch_op.drop_column("source_artifact_id")
