"""项目生命周期的持久化模型。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
    model_selection_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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
    source_assets: Mapped[list["SourceAssetModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    source_requirement_scope: Mapped["SourceRequirementScopeModel | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    source_recoveries: Mapped[list["SourceRecoveryModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    search_discovery_runs: Mapped[list["SearchDiscoveryRunModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    competitor_candidate_decisions: Mapped[list["CompetitorCandidateDecisionModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    competitor_source_onboardings: Mapped[list["CompetitorSourceOnboardingModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    competitor_material_discoveries: Mapped[list["CompetitorMaterialDiscoveryModel"]] = (
        relationship(back_populates="project", cascade="all, delete-orphan")
    )
    fragment_evidence_batches: Mapped[list["FragmentEvidenceBatchModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    parsed_artifacts: Mapped[list["ParsedArtifactModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    source_fragments: Mapped[list["SourceFragmentModel"]] = relationship(
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
    model_calls: Mapped[list["ModelCallModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    a2a_tasks: Mapped[list["A2ATaskModel"]] = relationship(
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
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    model_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped[ProjectModel] = relationship(back_populates="agent_runs")
    artifacts: Mapped[list["AgentArtifactModel"]] = relationship(back_populates="agent_run")
    model_calls: Mapped[list["ModelCallModel"]] = relationship(back_populates="agent_run")


class ModelCallModel(Base):
    """一次可审计的模型调用尝试，不保存原始 Prompt 或响应正文。"""

    __tablename__ = "model_calls"
    __table_args__ = (
        Index("ix_model_calls_project_created", "project_id", "created_at"),
        Index("ix_model_calls_run_attempt", "agent_run_id", "attempt_number"),
    )

    model_call_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    provider_model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_key: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="model_calls")
    agent_run: Mapped[AgentRunModel] = relationship(back_populates="model_calls")


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


class A2ATaskModel(Base):
    """竞品主管分派给一个 A2A 专家的独立、可恢复运行记录。"""

    __tablename__ = "a2a_tasks"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "parent_task_id",
            "specialist_type",
            name="uq_a2a_task_identity",
        ),
        Index("ix_a2a_tasks_project_status", "project_id", "status"),
    )

    a2a_task_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_task_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    specialist_type: Mapped[str] = mapped_column(String(40), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
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

    project: Mapped[ProjectModel] = relationship(back_populates="a2a_tasks")


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
    __table_args__ = (Index("ix_collection_jobs_project_status", "project_id", "status"),)

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
    evidence_records: Mapped[list["EvidenceModel"]] = relationship(back_populates="collection_job")
    source_asset: Mapped["SourceAssetModel | None"] = relationship(
        back_populates="collection_job", uselist=False
    )
    parsed_artifact: Mapped["ParsedArtifactModel | None"] = relationship(
        back_populates="collection_job", uselist=False, cascade="all, delete-orphan"
    )


class SourceAssetModel(Base):
    """用户明确提供并授权给当前研究项目使用的原始资料。"""

    __tablename__ = "source_assets"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "kind", "content_hash", name="uq_source_asset_project_kind_hash"
        ),
        UniqueConstraint("collection_job_id", name="uq_source_asset_collection_job"),
        Index("ix_source_assets_project_status", "project_id", "status"),
        Index("ix_source_assets_project_kind", "project_id", "kind"),
    )

    source_asset_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_job_id: Mapped[str] = mapped_column(
        ForeignKey("collection_jobs.collection_job_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    media_category: Mapped[str] = mapped_column(String(30), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    authorization_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    authorization_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    authorized_by: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="source_assets")
    collection_job: Mapped[CollectionJobModel] = relationship(back_populates="source_asset")
    parsed_artifacts: Mapped[list["ParsedArtifactModel"]] = relationship(
        back_populates="source_asset", cascade="all, delete-orphan"
    )


class SourceRoutingModel(Base):
    """一份资料的可审计多标签分发建议与人工确认结果。"""

    __tablename__ = "source_routings"
    __table_args__ = (
        UniqueConstraint("source_asset_id", name="uq_source_routing_source_asset"),
        Index("ix_source_routings_project_status", "project_id", "status"),
    )

    source_routing_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    suggestions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    confirmed_routes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confirmed_claim_types_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    rule_signals_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_call_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SourceRequirementScopeModel(Base):
    """用户确认的目标产品、竞品与资料准备度研究维度。"""

    __tablename__ = "source_requirement_scopes"
    __table_args__ = (UniqueConstraint("project_id", name="uq_source_requirement_scope_project"),)

    source_requirement_scope_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_products_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    competitors_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    dimensions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False)
    update_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="source_requirement_scope")


class SourceRecoveryModel(Base):
    """一次资料失败/不足后的用户补充编排记录。"""

    __tablename__ = "source_recoveries"
    __table_args__ = (
        Index("ix_source_recoveries_project_status", "project_id", "status"),
        Index("ix_source_recoveries_project_source", "project_id", "failed_source_asset_id"),
    )

    source_recovery_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    failed_source_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    failed_collection_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_jobs.collection_job_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_artifacts.artifact_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_gap_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_message: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requested_fields_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    affected_task_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    affected_agent_types_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    assessment_before_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    current_assessment_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    request_reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision_actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="source_recoveries")
    submissions: Mapped[list["SourceRecoverySubmissionModel"]] = relationship(
        back_populates="recovery", cascade="all, delete-orphan"
    )


class SourceRecoverySubmissionModel(Base):
    """用户一次结构化补充；正文只保存在可追溯 Source Fragment 中。"""

    __tablename__ = "source_recovery_submissions"
    __table_args__ = (
        UniqueConstraint(
            "source_recovery_id", "request_id", name="uq_source_recovery_submission_request"
        ),
        Index("ix_source_recovery_submissions_project_created", "project_id", "created_at"),
    )

    submission_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_recovery_id: Mapped[str] = mapped_column(
        ForeignKey("source_recoveries.source_recovery_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    submission_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="direct_answer"
    )
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    field_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    answer_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    recovery: Mapped[SourceRecoveryModel] = relationship(back_populates="submissions")


class SearchDiscoveryRunModel(Base):
    """一次搜索来源发现运行；候选结果明确不属于 Evidence。"""

    __tablename__ = "search_discovery_runs"
    __table_args__ = (
        Index("ix_search_discovery_runs_project_created", "project_id", "created_at"),
        Index("ix_search_discovery_runs_project_status", "project_id", "status"),
    )

    search_discovery_run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    intent: Mapped[str] = mapped_column(String(40), nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    include_domains_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    exclude_domains_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    candidates_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="search_discovery_runs")


class CompetitorCandidateDecisionModel(Base):
    """用户对一个版本化竞品候选 Artifact 的一次性 Gate 决定。"""

    __tablename__ = "competitor_candidate_decisions"
    __table_args__ = (
        UniqueConstraint("artifact_id", name="uq_competitor_candidate_decision_artifact"),
        Index("ix_competitor_candidate_decisions_project_created", "project_id", "created_at"),
    )

    decision_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("agent_artifacts.artifact_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    selected_proposal_ids_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="competitor_candidate_decisions")


class CompetitorSourceOnboardingModel(Base):
    """一次已确认竞品 Artifact 到 Source Asset 的原子接入批次。"""

    __tablename__ = "competitor_source_onboardings"
    __table_args__ = (
        UniqueConstraint("artifact_id", name="uq_competitor_source_onboarding_artifact"),
        Index("ix_competitor_source_onboardings_project_created", "project_id", "created_at"),
    )

    onboarding_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("agent_artifacts.artifact_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_candidate_decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    authorization_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    authorized_by: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="competitor_source_onboardings")
    items: Mapped[list["CompetitorSourceOnboardingItemModel"]] = relationship(
        back_populates="onboarding", cascade="all, delete-orphan"
    )


class CompetitorSourceOnboardingItemModel(Base):
    """候选 proposal/candidate 到具体 Source Asset 的不可变血缘。"""

    __tablename__ = "competitor_source_onboarding_items"
    __table_args__ = (
        UniqueConstraint(
            "onboarding_id",
            "candidate_id",
            name="uq_competitor_source_onboarding_candidate",
        ),
        Index(
            "ix_competitor_source_onboarding_items_project_asset",
            "project_id",
            "source_asset_id",
        ),
    )

    onboarding_item_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    onboarding_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_source_onboardings.onboarding_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposal_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_asset_created: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    onboarding: Mapped[CompetitorSourceOnboardingModel] = relationship(back_populates="items")
    source_asset: Mapped[SourceAssetModel] = relationship()


class CompetitorMaterialDiscoveryModel(Base):
    """按准确产品和研究维度执行的一批真实搜索发现。"""

    __tablename__ = "competitor_material_discoveries"
    __table_args__ = (
        Index("ix_competitor_material_discoveries_project_created", "project_id", "created_at"),
    )

    material_discovery_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False)
    max_results_per_query: Mapped[int] = mapped_column(Integer, nullable=False)
    products_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    dimensions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="competitor_material_discoveries")
    items: Mapped[list["CompetitorMaterialDiscoveryItemModel"]] = relationship(
        back_populates="discovery", cascade="all, delete-orphan"
    )
    decision: Mapped["CompetitorMaterialDecisionModel | None"] = relationship(
        back_populates="discovery", cascade="all, delete-orphan", uselist=False
    )


class CompetitorMaterialDiscoveryItemModel(Base):
    """发现批次内一个产品与一个维度对应的搜索运行。"""

    __tablename__ = "competitor_material_discovery_items"
    __table_args__ = (
        UniqueConstraint(
            "material_discovery_id",
            "product_role",
            "product_identity",
            "dimension",
            name="uq_competitor_material_discovery_plan",
        ),
    )

    material_discovery_item_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    material_discovery_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_material_discoveries.material_discovery_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_discovery_run_id: Mapped[str] = mapped_column(
        ForeignKey("search_discovery_runs.search_discovery_run_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    product_role: Mapped[str] = mapped_column(String(20), nullable=False)
    product_identity: Mapped[str] = mapped_column(String(500), nullable=False)
    product_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    discovery: Mapped[CompetitorMaterialDiscoveryModel] = relationship(back_populates="items")
    search_run: Mapped[SearchDiscoveryRunModel] = relationship()


class CompetitorMaterialDecisionModel(Base):
    """对一个资料发现批次的一次性人工 Gate 决定。"""

    __tablename__ = "competitor_material_decisions"
    __table_args__ = (
        UniqueConstraint("material_discovery_id", name="uq_competitor_material_decision_discovery"),
    )

    material_decision_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    material_discovery_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_material_discoveries.material_discovery_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_candidate_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    authorization_basis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    authorization_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    discovery: Mapped[CompetitorMaterialDiscoveryModel] = relationship(back_populates="decision")
    selections: Mapped[list["CompetitorMaterialSelectionModel"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )


class CompetitorMaterialSelectionModel(Base):
    """被确认候选到 Source Asset 的不可变产品/维度血缘。"""

    __tablename__ = "competitor_material_selections"
    __table_args__ = (
        UniqueConstraint(
            "material_decision_id",
            "candidate_id",
            name="uq_competitor_material_selection_candidate",
        ),
        Index("ix_competitor_material_selections_project_asset", "project_id", "source_asset_id"),
    )

    material_selection_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    material_decision_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_material_decisions.material_decision_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_discovery_item_id: Mapped[str] = mapped_column(
        ForeignKey(
            "competitor_material_discovery_items.material_discovery_item_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_discovery_run_id: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_role: Mapped[str] = mapped_column(String(20), nullable=False)
    product_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_asset_created: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    decision: Mapped[CompetitorMaterialDecisionModel] = relationship(back_populates="selections")
    source_asset: Mapped[SourceAssetModel] = relationship()


class FragmentEvidenceBatchModel(Base):
    """一批经过确定性准备、等待一次性人工 Gate 的 Evidence Draft。"""

    __tablename__ = "fragment_evidence_batches"
    __table_args__ = (
        Index("ix_fragment_evidence_batches_project_created", "project_id", "created_at"),
    )

    fragment_evidence_batch_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_asset_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    fragment_evidence_decision_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, unique=True
    )
    decision_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    selected_item_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="fragment_evidence_batches")
    items: Mapped[list["FragmentEvidenceBatchItemModel"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class FragmentEvidenceBatchItemModel(Base):
    """Evidence Draft、血缘约束和最终晋级结果。"""

    __tablename__ = "fragment_evidence_batch_items"
    __table_args__ = (
        UniqueConstraint(
            "fragment_evidence_batch_id",
            "source_fragment_id",
            name="uq_fragment_evidence_batch_fragment",
        ),
        Index(
            "ix_fragment_evidence_batch_items_project_fragment",
            "project_id",
            "source_fragment_id",
        ),
    )

    fragment_evidence_item_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    fragment_evidence_batch_id: Mapped[str] = mapped_column(
        ForeignKey("fragment_evidence_batches.fragment_evidence_batch_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_fragment_id: Mapped[str] = mapped_column(
        ForeignKey("source_fragments.source_fragment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    eligibility: Mapped[str] = mapped_column(String(30), nullable=False)
    block_reasons_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confirmed_routes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allowed_claim_types_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    suggested_claim_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    product_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    product_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dimensions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    authority_score: Mapped[float] = mapped_column(Float, nullable=False)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False)
    diversity_score: Mapped[float] = mapped_column(Float, nullable=False)
    quality_reasons_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    existing_evidence_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected_claim_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_segment: Mapped[str | None] = mapped_column(String(160), nullable=True)
    promotion_status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence.evidence_id", ondelete="SET NULL"), nullable=True, index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    batch: Mapped[FragmentEvidenceBatchModel] = relationship(back_populates="items")
    source_fragment: Mapped["SourceFragmentModel"] = relationship()
    evidence: Mapped["EvidenceModel | None"] = relationship()


class ParsedArtifactModel(Base):
    """A deterministic parser result whose fragments have passed source verification."""

    __tablename__ = "parsed_artifacts"
    __table_args__ = (
        UniqueConstraint("collection_job_id", name="uq_parsed_artifact_collection_job"),
        Index("ix_parsed_artifacts_project_source", "project_id", "source_asset_id"),
    )

    parsed_artifact_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_job_id: Mapped[str] = mapped_column(
        ForeignKey("collection_jobs.collection_job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parser_id: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fragment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="parsed_artifacts")
    source_asset: Mapped[SourceAssetModel] = relationship(back_populates="parsed_artifacts")
    collection_job: Mapped[CollectionJobModel] = relationship(back_populates="parsed_artifact")
    fragments: Mapped[list["SourceFragmentModel"]] = relationship(
        back_populates="parsed_artifact", cascade="all, delete-orphan"
    )


class SourceFragmentModel(Base):
    """An exact excerpt and deterministic locator into one parsed source snapshot."""

    __tablename__ = "source_fragments"
    __table_args__ = (
        UniqueConstraint(
            "parsed_artifact_id", "ordinal", name="uq_source_fragment_artifact_ordinal"
        ),
        Index("ix_source_fragments_project_source", "project_id", "source_asset_id"),
    )

    source_fragment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    parsed_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("parsed_artifacts.parsed_artifact_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    locator_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    original_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    parsed_artifact: Mapped[ParsedArtifactModel] = relationship(back_populates="fragments")
    project: Mapped[ProjectModel] = relationship(back_populates="source_fragments")


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
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_assets.source_asset_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_fragment_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_fragments.source_fragment_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_locator_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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
    score_breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
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
