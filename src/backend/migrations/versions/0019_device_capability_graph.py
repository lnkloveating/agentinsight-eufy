"""Add evidence-backed device capability graph and household snapshots.

Revision ID: 0019_device_capability_graph
Revises: 0018_universal_agent_recovery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_device_capability_graph"
down_revision: str | None = "0018_universal_agent_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_catalog",
        sa.Column("catalog_device_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column("identity_evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("catalog_device_id"),
        sa.UniqueConstraint(
            "project_id", "manufacturer", "model", name="uq_device_catalog_project_model"
        ),
    )
    op.create_index(
        "ix_device_catalog_project_id", "device_catalog", ["project_id"], unique=False
    )
    op.create_index(
        "ix_device_catalog_project_category",
        "device_catalog",
        ["project_id", "category"],
        unique=False,
    )

    op.create_table(
        "device_capability_claims",
        sa.Column("capability_claim_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("catalog_device_id", sa.String(length=40), nullable=False),
        sa.Column("capability_key", sa.String(length=80), nullable=False),
        sa.Column("capability_name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("assertion", sa.String(length=20), nullable=False),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("latency_ms_max", sa.Integer(), nullable=True),
        sa.Column("data_scope", sa.String(length=30), nullable=False),
        sa.Column("authorization_required", sa.Boolean(), nullable=False),
        sa.Column("offline_support", sa.String(length=20), nullable=False),
        sa.Column("fallback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_device_id"],
            ["device_catalog.catalog_device_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("capability_claim_id"),
    )
    op.create_index(
        "ix_device_capability_claims_catalog_device_id",
        "device_capability_claims",
        ["catalog_device_id"],
        unique=False,
    )
    op.create_index(
        "ix_device_capability_claims_project_id",
        "device_capability_claims",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_device_capability_project_key",
        "device_capability_claims",
        ["project_id", "capability_key"],
        unique=False,
    )
    op.create_index(
        "ix_device_capability_catalog_key",
        "device_capability_claims",
        ["catalog_device_id", "capability_key"],
        unique=False,
    )

    op.create_table(
        "household_device_snapshots",
        sa.Column("snapshot_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("authorization_confirmed", sa.Boolean(), nullable=False),
        sa.Column("authorized_by", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("locations_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint("project_id", "version", name="uq_household_snapshot_version"),
    )
    op.create_index(
        "ix_household_device_snapshots_project_id",
        "household_device_snapshots",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_household_device_snapshots_status",
        "household_device_snapshots",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_household_snapshot_project_status",
        "household_device_snapshots",
        ["project_id", "status"],
        unique=False,
    )

    op.create_table(
        "household_devices",
        sa.Column("household_device_record_id", sa.String(length=40), nullable=False),
        sa.Column("household_device_id", sa.String(length=80), nullable=False),
        sa.Column("snapshot_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("catalog_device_id", sa.String(length=40), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("location_id", sa.String(length=80), nullable=False),
        sa.Column("runtime_status", sa.String(length=20), nullable=False),
        sa.Column("authorization_status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_device_id"], ["device_catalog.catalog_device_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["household_device_snapshots.snapshot_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("household_device_record_id"),
        sa.UniqueConstraint(
            "snapshot_id", "household_device_id", name="uq_household_snapshot_device"
        ),
    )
    op.create_index(
        "ix_household_devices_catalog_device_id",
        "household_devices",
        ["catalog_device_id"],
        unique=False,
    )
    op.create_index(
        "ix_household_devices_project_id",
        "household_devices",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_household_devices_snapshot_id",
        "household_devices",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_household_device_project_location",
        "household_devices",
        ["project_id", "location_id"],
        unique=False,
    )

    op.create_table(
        "household_device_relations",
        sa.Column("relation_record_id", sa.String(length=40), nullable=False),
        sa.Column("relation_id", sa.String(length=80), nullable=False),
        sa.Column("snapshot_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("source_household_device_id", sa.String(length=80), nullable=False),
        sa.Column("target_household_device_id", sa.String(length=80), nullable=False),
        sa.Column("relation_type", sa.String(length=30), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["household_device_snapshots.snapshot_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("relation_record_id"),
        sa.UniqueConstraint("snapshot_id", "relation_id", name="uq_household_relation"),
    )
    op.create_index(
        "ix_household_device_relations_project_id",
        "household_device_relations",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_household_device_relations_snapshot_id",
        "household_device_relations",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_household_relation_project_type",
        "household_device_relations",
        ["project_id", "relation_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_household_relation_project_type", table_name="household_device_relations"
    )
    op.drop_index(
        "ix_household_device_relations_snapshot_id", table_name="household_device_relations"
    )
    op.drop_index(
        "ix_household_device_relations_project_id", table_name="household_device_relations"
    )
    op.drop_table("household_device_relations")

    op.drop_index("ix_household_device_project_location", table_name="household_devices")
    op.drop_index("ix_household_devices_snapshot_id", table_name="household_devices")
    op.drop_index("ix_household_devices_project_id", table_name="household_devices")
    op.drop_index("ix_household_devices_catalog_device_id", table_name="household_devices")
    op.drop_table("household_devices")

    op.drop_index(
        "ix_household_snapshot_project_status", table_name="household_device_snapshots"
    )
    op.drop_index(
        "ix_household_device_snapshots_status", table_name="household_device_snapshots"
    )
    op.drop_index(
        "ix_household_device_snapshots_project_id", table_name="household_device_snapshots"
    )
    op.drop_table("household_device_snapshots")

    op.drop_index(
        "ix_device_capability_catalog_key", table_name="device_capability_claims"
    )
    op.drop_index(
        "ix_device_capability_project_key", table_name="device_capability_claims"
    )
    op.drop_index(
        "ix_device_capability_claims_project_id", table_name="device_capability_claims"
    )
    op.drop_index(
        "ix_device_capability_claims_catalog_device_id",
        table_name="device_capability_claims",
    )
    op.drop_table("device_capability_claims")

    op.drop_index("ix_device_catalog_project_category", table_name="device_catalog")
    op.drop_index("ix_device_catalog_project_id", table_name="device_catalog")
    op.drop_table("device_catalog")
