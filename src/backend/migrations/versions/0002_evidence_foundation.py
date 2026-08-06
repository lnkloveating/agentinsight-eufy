"""建立证据湖、采集任务与声明关系表。

Revision ID: 0002_evidence_foundation
Revises: 0001_project_lifecycle
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_evidence_foundation"
down_revision: str | None = "0001_project_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_jobs",
        sa.Column("collection_job_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("collection_job_id"),
    )
    op.create_index("ix_collection_jobs_project_id", "collection_jobs", ["project_id"])
    op.create_index("ix_collection_jobs_task_id", "collection_jobs", ["task_id"])
    op.create_index("ix_collection_jobs_status", "collection_jobs", ["status"])
    op.create_index(
        "ix_collection_jobs_project_status", "collection_jobs", ["project_id", "status"]
    )

    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("collection_job_id", sa.String(length=40), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("normalized_source_url", sa.Text(), nullable=False),
        sa.Column("source_domain", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("original_excerpt", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=False),
        sa.Column("product", sa.String(length=160), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("user_segment", sa.String(length=160), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("authority_score", sa.Float(), nullable=False),
        sa.Column("recency_score", sa.Float(), nullable=False),
        sa.Column("diversity_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_job_id"], ["collection_jobs.collection_job_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_id"),
        sa.UniqueConstraint("project_id", "content_hash", name="uq_evidence_project_hash"),
    )
    op.create_index("ix_evidence_project_id", "evidence", ["project_id"])
    op.create_index("ix_evidence_collection_job_id", "evidence", ["collection_job_id"])
    op.create_index("ix_evidence_status", "evidence", ["status"])
    op.create_index("ix_evidence_project_status", "evidence", ["project_id", "status"])
    op.create_index(
        "ix_evidence_project_source_type", "evidence", ["project_id", "source_type"]
    )

    op.create_table(
        "claims",
        sa.Column("claim_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("claim_id"),
    )
    op.create_index("ix_claims_project_id", "claims", ["project_id"])
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_index("ix_claims_project_status", "claims", ["project_id", "status"])

    op.create_table(
        "claim_evidence_links",
        sa.Column("link_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("claim_id", sa.String(length=40), nullable=False),
        sa.Column("evidence_id", sa.String(length=40), nullable=False),
        sa.Column("relationship", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.evidence_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("link_id"),
        sa.UniqueConstraint(
            "claim_id", "evidence_id", "relationship", name="uq_claim_evidence_relationship"
        ),
    )
    op.create_index("ix_claim_evidence_project", "claim_evidence_links", ["project_id"])
    op.create_index("ix_claim_evidence_claim_id", "claim_evidence_links", ["claim_id"])
    op.create_index("ix_claim_evidence_evidence_id", "claim_evidence_links", ["evidence_id"])


def downgrade() -> None:
    op.drop_table("claim_evidence_links")
    op.drop_table("claims")
    op.drop_table("evidence")
    op.drop_table("collection_jobs")
