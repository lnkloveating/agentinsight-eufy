"""资料自动处理失败后的用户补充与定向恢复契约。"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.evidence import EvidenceClaimType
from app.schemas.source import SourceAuthorizationBasis
from app.schemas.source_requirements import ProductReference, SourceRequirementAssessment
from app.schemas.source_routing import SourceRouteTarget


class RecoverableAgentType(StrEnum):
    USER_RESEARCH = "user_research"
    COMPETITOR_RESEARCH = "competitor_research"
    PRODUCT_TECHNICAL = "product_technical"
    COMMERCIAL_EVALUATION = "commercial_evaluation"
    RED_TEAM = "red_team"
    CANDIDATE_SYNTHESIS = "candidate_synthesis"
    VALIDATION = "validation"
    FINAL_SYNTHESIS = "final_synthesis"


_RECOVERABLE_AGENT_TYPES = {item.value for item in RecoverableAgentType}


class SourceRecoveryStatus(StrEnum):
    WAITING_FOR_USER_INPUT = "waiting_for_user_input"
    NEEDS_MORE_INFORMATION = "needs_more_information"
    RESOLVED = "resolved"
    PROCEEDING_WITH_GAPS = "proceeding_with_gaps"
    CANCELLED = "cancelled"


class SourceRecoveryReasonCode(StrEnum):
    ROBOTS_BLOCKED = "robots_blocked"
    AUTHENTICATION_REQUIRED = "authentication_required"
    ACCESS_DENIED = "access_denied"
    RATE_LIMITED = "rate_limited"
    CONNECTOR_UNAVAILABLE = "connector_unavailable"
    UNSUPPORTED_MEDIA = "unsupported_media"
    PROCESSING_FAILED = "processing_failed"
    EMPTY_CONTENT = "empty_content"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class SourceRecoveryDecisionAction(StrEnum):
    PROCEED_WITH_GAPS = "proceed_with_gaps"
    CANCEL = "cancel"


class SourceRecoveryResumeMode(StrEnum):
    NONE = "none"
    TARGETED_RETRY = "targeted_retry"
    PROCEED_WITH_GAPS = "proceed_with_gaps"


class SourceRecoverySubmissionKind(StrEnum):
    DIRECT_ANSWER = "direct_answer"
    EXISTING_EVIDENCE = "existing_evidence"


class SourceRecoveryCreate(BaseModel):
    source_asset_id: str = Field(min_length=1, max_length=40)
    requirement_ids: list[str] = Field(default_factory=list, max_length=30)
    missing_questions: list[str] = Field(default_factory=list, max_length=20)
    affected_task_ids: list[str] = Field(default_factory=list, max_length=30)
    affected_agent_types: list[str] = Field(default_factory=list, max_length=10)
    requested_by: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator(
        "requirement_ids", "affected_task_ids", "affected_agent_types", "missing_questions"
    )
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source recovery identifiers must be unique")
        return value

    @field_validator("missing_questions", mode="before")
    @classmethod
    def strip_questions(cls, value: object) -> object:
        if isinstance(value, list):
            return [item.strip() if isinstance(item, str) else item for item in value]
        return value

    @field_validator("affected_agent_types")
    @classmethod
    def known_agent_types(cls, value: list[str]) -> list[str]:
        invalid = sorted(set(value) - _RECOVERABLE_AGENT_TYPES)
        if invalid:
            raise ValueError(f"source recovery contains unknown agent types: {invalid}")
        return value


class AgentArtifactSourceRecoveryCreate(BaseModel):
    gap_ids: list[str] = Field(default_factory=list, max_length=30)
    requested_by: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("gap_ids")
    @classmethod
    def unique_gap_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("agent artifact recovery gap_ids must be unique")
        return value


class ProductTechnicalSourceRecoveryCreate(AgentArtifactSourceRecoveryCreate):
    """向后兼容原产品技术专用接口。"""


class AgentGapSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class AgentArtifactGap(BaseModel):
    gap_id: str = Field(min_length=1, max_length=80)
    artifact_id: str = Field(min_length=1, max_length=80)
    task_id: str = Field(min_length=1, max_length=80)
    agent_type: RecoverableAgentType
    question: str = Field(min_length=1, max_length=1500)
    reason: str = Field(min_length=1, max_length=1500)
    severity: AgentGapSeverity
    recommended_source_types: list[str] = Field(default_factory=list, max_length=20)
    required_evidence_types: list[str] = Field(default_factory=list, max_length=20)
    affected_candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    scope_label: str | None = Field(default=None, max_length=240)
    dimension: str | None = Field(default=None, max_length=120)
    source_path: str = Field(min_length=1, max_length=500)

    @field_validator(
        "recommended_source_types", "required_evidence_types", "affected_candidate_ids"
    )
    @classmethod
    def unique_gap_lists(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("agent gap list values must be unique")
        return value


class AgentArtifactGapPage(BaseModel):
    artifact_id: str
    agent_type: RecoverableAgentType
    items: list[AgentArtifactGap]
    total: int = Field(ge=0)


class SourceRecoveryRequestedField(BaseModel):
    field_id: str = Field(min_length=1, max_length=80)
    requirement_id: str = Field(min_length=1, max_length=120)
    field_key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=500)
    required: bool
    claim_type: EvidenceClaimType
    evidence_type_hint: str | None = Field(default=None, max_length=120)
    affected_candidate_ids: list[str] = Field(default_factory=list, max_length=5)
    product: ProductReference | None = None
    region: str | None = Field(default=None, max_length=120)
    route: SourceRouteTarget | None = None


class SourceRecoveryAnswer(BaseModel):
    field_id: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=10_000)
    source_note: str | None = Field(default=None, max_length=1000)

    @field_validator("value", "source_note", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SourceRecoverySubmissionCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    answers: list[SourceRecoveryAnswer] = Field(min_length=1, max_length=30)
    actor: str = Field(min_length=1, max_length=120)
    authorization_basis: SourceAuthorizationBasis
    authorization_confirmed: Literal[True]
    accuracy_confirmed: Literal[True]

    @model_validator(mode="after")
    def unique_answer_fields(self) -> "SourceRecoverySubmissionCreate":
        field_ids = [answer.field_id for answer in self.answers]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("source recovery answers must use unique field ids")
        return self


class SourceRecoveryEvidenceBinding(BaseModel):
    field_id: str = Field(min_length=1, max_length=80)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence binding ids must be unique")
        return value


class SourceRecoveryEvidenceSubmissionCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    source_asset_id: str = Field(min_length=1, max_length=40)
    bindings: list[SourceRecoveryEvidenceBinding] = Field(min_length=1, max_length=30)
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_bound_fields(self) -> "SourceRecoveryEvidenceSubmissionCreate":
        field_ids = [binding.field_id for binding in self.bindings]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("evidence bindings must use unique field ids")
        return self


class SourceRecoverySubmission(BaseModel):
    submission_id: str
    request_id: str
    submission_kind: SourceRecoverySubmissionKind
    source_asset_id: str
    field_ids: list[str]
    evidence_ids: list[str]
    answer_count: int = Field(ge=1)
    actor: str
    created_at: datetime


class SourceRecoveryResumeDirective(BaseModel):
    ready: bool
    mode: SourceRecoveryResumeMode
    affected_task_ids: list[str] = Field(default_factory=list)
    affected_agent_types: list[str] = Field(default_factory=list)
    reason: str


class SourceRecoveryDecisionCreate(BaseModel):
    action: SourceRecoveryDecisionAction
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)


class SourceRecovery(BaseModel):
    source_recovery_id: str
    project_id: str
    status: SourceRecoveryStatus
    reason_code: SourceRecoveryReasonCode
    reason_message: str
    failed_source_asset_id: str | None = None
    failed_collection_job_id: str | None = None
    source_artifact_id: str | None = None
    source_gap_ids: list[str] = Field(default_factory=list)
    requirement_ids: list[str]
    requested_fields: list[SourceRecoveryRequestedField]
    affected_task_ids: list[str]
    affected_agent_types: list[str]
    assessment_before: SourceRequirementAssessment
    current_assessment: SourceRequirementAssessment
    submissions: list[SourceRecoverySubmission]
    resume_directive: SourceRecoveryResumeDirective
    requested_by: str
    request_reason: str
    decision_actor: str | None = None
    decision_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class SourceRecoveryPage(BaseModel):
    items: list[SourceRecovery]
    total: int = Field(ge=0)
