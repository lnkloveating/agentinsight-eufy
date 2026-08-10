"""Public contracts for the pre-project Research Brief clarification dialogue."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.project import (
    AllowedIntervention,
    AuthorizedSignalType,
    HomeSafetyDomain,
    ResearchBrief,
    ResearchDeliverable,
    ResearchScope,
)


class StrictClarificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClarificationStatus(StrEnum):
    AWAITING_USER = "awaiting_user"
    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    FAILED = "failed"


class ClarificationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ClarificationMessage(StrictClarificationModel):
    message_id: str
    role: ClarificationRole
    content: str = Field(min_length=1, max_length=8_000)
    created_at: datetime


class ResearchSourcePermissionsDraft(StrictClarificationModel):
    public_sources: bool | None = None
    user_uploaded_materials: bool | None = None
    enterprise_internal_materials: bool | None = None
    authorized_household_events: bool | None = None


class ResearchPrivacyBoundaryDraft(StrictClarificationModel):
    raw_media_allowed: bool | None = None
    restricted_zones: list[str] | None = Field(default=None, max_length=30)
    retention_policy: str | None = Field(default=None, min_length=1, max_length=1_000)
    external_sharing_allowed: bool | None = None


class ResearchInterventionBoundaryDraft(StrictClarificationModel):
    allowed_interventions: list[AllowedIntervention] | None = Field(
        default=None, min_length=1, max_length=6
    )
    prohibited_actions: list[str] | None = Field(default=None, min_length=1, max_length=30)
    high_impact_action_requires_human_approval: Literal[True] | None = None


class ResearchBriefDraft(StrictClarificationModel):
    """A typed partial brief. Missing values stay absent instead of receiving model defaults."""

    question: str | None = Field(default=None, min_length=5, max_length=1_000)
    research_scope: ResearchScope | None = None
    safety_domains: list[HomeSafetyDomain] | None = Field(default=None, min_length=1, max_length=6)
    target_ecosystems: list[str] | None = Field(default=None, min_length=1, max_length=10)
    comparison_ecosystems: list[str] | None = Field(default=None, max_length=20)
    target_users: list[str] | None = Field(default=None, min_length=1, max_length=20)
    markets: list[str] | None = Field(default=None, min_length=1, max_length=20)
    time_horizon: str | None = Field(default=None, min_length=1, max_length=120)
    safety_goals: list[str] | None = Field(default=None, min_length=1, max_length=20)
    risk_scenarios: list[str] | None = Field(default=None, min_length=1, max_length=30)
    authorized_signal_types: list[AuthorizedSignalType] | None = Field(
        default=None, min_length=1, max_length=8
    )
    privacy_boundary: ResearchPrivacyBoundaryDraft | None = None
    intervention_boundary: ResearchInterventionBoundaryDraft | None = None
    forbidden_inferences: list[str] | None = Field(default=None, min_length=1, max_length=30)
    evaluation_dimensions: list[str] | None = Field(default=None, min_length=1, max_length=30)
    validation_expectations: list[str] | None = Field(default=None, min_length=1, max_length=30)
    source_permissions: ResearchSourcePermissionsDraft | None = None
    deliverables: list[ResearchDeliverable] | None = Field(default=None, min_length=1, max_length=4)


class ClarificationQuestion(StrictClarificationModel):
    question_id: str = Field(min_length=1, max_length=80)
    field_paths: list[str] = Field(min_length=1, max_length=8)
    prompt: str = Field(min_length=1, max_length=1_000)
    choices: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("field_paths", "choices")
    @classmethod
    def unique_non_blank(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("values must not contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("values must not contain duplicates")
        return normalized


class BriefClarificationStart(StrictClarificationModel):
    initial_question: str = Field(min_length=5, max_length=1_000)
    model_id: str | None = Field(default=None, min_length=3, max_length=120)


class BriefClarificationAnswer(StrictClarificationModel):
    message: str = Field(min_length=1, max_length=8_000)
    expected_version: int = Field(ge=1)


class BriefClarificationSession(StrictClarificationModel):
    session_id: str
    status: ClarificationStatus
    version: int = Field(ge=1)
    model_id: str
    messages: list[ClarificationMessage]
    draft: ResearchBriefDraft
    missing_fields: list[str]
    validation_issues: list[str]
    questions: list[ClarificationQuestion]
    completed_brief: ResearchBrief | None = None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_microusd: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class ClarifierFieldEvidence(StrictClarificationModel):
    field_path: str = Field(min_length=1, max_length=120)
    message_ids: list[str] = Field(min_length=1, max_length=20)


class BriefClarifierModelOutput(StrictClarificationModel):
    """Structured model output; deterministic service remains authoritative."""

    assistant_message: str = Field(min_length=1, max_length=4_000)
    draft_patch: ResearchBriefDraft = Field(default_factory=ResearchBriefDraft)
    field_evidence: list[ClarifierFieldEvidence] = Field(default_factory=list, max_length=80)
    questions: list[ClarificationQuestion] = Field(default_factory=list, max_length=6)
