"""项目生命周期的持久化模型。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(UTC)


class ProjectModel(Base):
    """研究项目及其当前状态。"""

    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    current_stage: Mapped[str] = mapped_column(String(80), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    brief_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pending_decision_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    agent_runs: Mapped[list["AgentRunModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["AgentArtifactModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    events: Mapped[list["ProjectEventModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["DecisionModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    collection_jobs: Mapped[list["CollectionJobModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    evidence_records: Mapped[list["EvidenceModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    claims: Mapped[list["ClaimModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    innovations: Mapped[list["InnovationModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class AgentRunModel(Base):
    """一个 Agent 在项目中的运行记录。"""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_project_status", "project_id", "status"),)

    agent_run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    adapter_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    workspace_key: Mapped[str | None] = mapped_column(String(240), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    timeout_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_artifact_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    output_artifact_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    unknowns_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="agent_runs")
    artifacts: Mapped[list["AgentArtifactModel"]] = relationship(back_populates="agent_run")


class AgentArtifactModel(Base):
    """不可覆盖、带版本和血缘的结构化 Agent 交付物。"""

    __tablename__ = "agent_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "task_id",
            "artifact_type",
            "version",
            name="uq_agent_artifact_version",
        ),
        Index("ix_agent_artifacts_project_task", "project_id", "task_id"),
    )

    artifact_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    contradictions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    unknowns_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    errors_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_artifact_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="artifacts")
    agent_run: Mapped[AgentRunModel] = relationship(back_populates="artifacts")


class ProjectEventModel(Base):
    """可回放的项目领域事件。"""

    __tablename__ = "project_events"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence_number", name="uq_project_event_sequence"),
        Index("ix_project_events_project_created", "project_id", "created_at"),
    )

    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="events")


class DecisionModel(Base):
    """人工审批和流程恢复决定。"""

    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_project_created", "project_id", "created_at"),)

    decision_record_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    selected_concept_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="decisions")


class CollectionJobModel(Base):
    """一次外部资料采集尝试，包括失败和降级结果。"""

    __tablename__ = "collection_jobs"
    __table_args__ = (
        Index("ix_collection_jobs_project_status", "project_id", "status"),
    )

    collection_job_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="collection_jobs")
    evidence_records: Mapped[list["EvidenceModel"]] = relationship(
        back_populates="collection_job"
    )


class EvidenceModel(Base):
    """可回溯到原始来源、可供 Claim Gate 校验的证据记录。"""

    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("project_id", "content_hash", name="uq_evidence_project_hash"),
        Index("ix_evidence_project_status", "project_id", "status"),
        Index("ix_evidence_project_source_type", "project_id", "source_type"),
    )

    evidence_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_jobs.collection_job_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    original_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), nullable=False)
    product: Mapped[str | None] = mapped_column(String(160), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_segment: Mapped[str | None] = mapped_column(String(160), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    authority_score: Mapped[float] = mapped_column(Float, nullable=False)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False)
    diversity_score: Mapped[float] = mapped_column(Float, nullable=False)

    project: Mapped[ProjectModel] = relationship(back_populates="evidence_records")
    collection_job: Mapped[CollectionJobModel | None] = relationship(
        back_populates="evidence_records"
    )
    claim_links: Mapped[list["ClaimEvidenceLinkModel"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )


class ClaimModel(Base):
    """Agent 提出的事实、观点、推断或待验证假设。"""

    __tablename__ = "claims"
    __table_args__ = (Index("ix_claims_project_status", "project_id", "status"),)

    claim_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="claims")
    evidence_links: Mapped[list["ClaimEvidenceLinkModel"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimEvidenceLinkModel(Base):
    """Claim 与 Evidence 之间的支持或反驳关系。"""

    __tablename__ = "claim_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "claim_id", "evidence_id", "relationship", name="uq_claim_evidence_relationship"
        ),
        Index("ix_claim_evidence_project", "project_id"),
    )

    link_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.claim_id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence.evidence_id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column("relationship", String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    claim: Mapped[ClaimModel] = relationship(back_populates="evidence_links")
    evidence: Mapped[EvidenceModel] = relationship(back_populates="claim_links")


class InnovationModel(Base):
    """一个可审计、可评分、可被红队改变结论的未来产品候选。"""

    __tablename__ = "innovations"
    __table_args__ = (Index("ix_innovations_project_status", "project_id", "status"),)

    innovation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_user_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    problem_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    event_understanding_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    competitor_gap_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    technical_assessment_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    business_assessment_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    red_team_review_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    score_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    base_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    gate_issues_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="innovations")
