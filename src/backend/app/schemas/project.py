from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.model import ModelSelection


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_BRIEF_APPROVAL = "awaiting_brief_approval"
    RESEARCHING = "researching"
    AWAITING_CONCEPT_APPROVAL = "awaiting_concept_approval"
    SUPPLEMENTING_RESEARCH = "supplementing_research"
    GENERATING_REPORT = "generating_report"
    AWAITING_FINAL_APPROVAL = "awaiting_final_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_REVISION = "needs_revision"
    CANCELLED = "cancelled"


class DecisionAction(StrEnum):
    APPROVE = "approve"
    REVISE = "revise"
    RESEARCH_MORE = "research_more"
    REJECT = "reject"
    TERMINATE = "terminate"


class ResearchScope(StrEnum):
    HOME_SAFETY_ECOSYSTEM = "home_safety_ecosystem"


class HomeSafetyDomain(StrEnum):
    GENERAL_HOME_SAFETY = "general_home_safety"
    PROPERTY_SECURITY = "property_security"
    PERSONAL_SAFETY = "personal_safety"
    ELDER_SAFETY = "elder_safety"
    CHILD_SAFETY = "child_safety"
    PERIMETER_SAFETY = "perimeter_safety"


class AuthorizedSignalType(StrEnum):
    VISUAL_EVENT_METADATA = "visual_event_metadata"
    MOTION_EVENT = "motion_event"
    DOOR_EVENT = "door_event"
    DEVICE_STATUS = "device_status"
    HOUSEHOLD_PRESENCE = "household_presence"
    USER_CONFIRMATION = "user_confirmation"
    ENVIRONMENT_CONTEXT = "environment_context"
    SIMULATED_EVENT = "simulated_event"


class AllowedIntervention(StrEnum):
    CONTINUE_OBSERVING = "continue_observing"
    REQUEST_ADDITIONAL_SIGNAL = "request_additional_signal"
    LOCAL_PROMPT = "local_prompt"
    ASK_USER = "ask_user"
    NOTIFY_AUTHORIZED_CONTACT = "notify_authorized_contact"
    PRESERVE_EVIDENCE = "preserve_evidence"


class ResearchDeliverable(StrEnum):
    ECOSYSTEM_OPPORTUNITY_PORTFOLIO = "ecosystem_opportunity_portfolio"
    DEVICE_CAPABILITY_GAP = "device_capability_gap"
    POLICY_DRY_RUN = "policy_dry_run"
    PILOT_RECOMMENDATION = "pilot_recommendation"


class StrictProjectModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchSourcePermissions(StrictProjectModel):
    public_sources: bool
    user_uploaded_materials: bool
    enterprise_internal_materials: bool
    authorized_household_events: bool


class ResearchPrivacyBoundary(StrictProjectModel):
    raw_media_allowed: bool
    restricted_zones: list[str] = Field(max_length=30)
    retention_policy: str = Field(min_length=1, max_length=1000)
    external_sharing_allowed: bool

    @field_validator("restricted_zones")
    @classmethod
    def validate_restricted_zones(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value, field_name="restricted_zones", max_length=200)


class ResearchInterventionBoundary(StrictProjectModel):
    allowed_interventions: list[AllowedIntervention] = Field(min_length=1, max_length=6)
    prohibited_actions: list[str] = Field(min_length=1, max_length=30)
    high_impact_action_requires_human_approval: Literal[True]

    @field_validator("allowed_interventions")
    @classmethod
    def validate_allowed_interventions(
        cls, value: list[AllowedIntervention]
    ) -> list[AllowedIntervention]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_interventions must not contain duplicates")
        return value

    @field_validator("prohibited_actions")
    @classmethod
    def validate_prohibited_actions(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value, field_name="prohibited_actions", max_length=300)


def _normalize_unique_strings(
    values: list[str], *, field_name: str, max_length: int
) -> list[str]:
    normalized = [value.strip() for value in values]
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain blank values")
    if any(len(value) > max_length for value in normalized):
        raise ValueError(f"{field_name} values must be at most {max_length} characters")
    folded = [value.casefold() for value in normalized]
    if len(folded) != len(set(folded)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


class ResearchBrief(StrictProjectModel):
    question: str = Field(min_length=5, max_length=1000)
    research_scope: ResearchScope
    safety_domains: list[HomeSafetyDomain] = Field(min_length=1, max_length=6)
    target_ecosystems: list[str] = Field(min_length=1, max_length=10)
    comparison_ecosystems: list[str] = Field(max_length=20)
    target_users: list[str] = Field(min_length=1, max_length=20)
    markets: list[str] = Field(min_length=1, max_length=20)
    time_horizon: str = Field(min_length=1, max_length=120)
    safety_goals: list[str] = Field(min_length=1, max_length=20)
    risk_scenarios: list[str] = Field(min_length=1, max_length=30)
    authorized_signal_types: list[AuthorizedSignalType] = Field(min_length=1, max_length=8)
    privacy_boundary: ResearchPrivacyBoundary
    intervention_boundary: ResearchInterventionBoundary
    forbidden_inferences: list[str] = Field(min_length=1, max_length=30)
    evaluation_dimensions: list[str] = Field(min_length=1, max_length=30)
    validation_expectations: list[str] = Field(min_length=1, max_length=30)
    source_permissions: ResearchSourcePermissions
    deliverables: list[ResearchDeliverable] = Field(min_length=1, max_length=4)

    @field_validator(
        "target_ecosystems",
        "comparison_ecosystems",
        "target_users",
        "markets",
        "safety_goals",
        "risk_scenarios",
        "forbidden_inferences",
        "evaluation_dimensions",
        "validation_expectations",
    )
    @classmethod
    def normalize_string_lists(cls, value: list[str], info: Any) -> list[str]:
        limits = {
            "target_ecosystems": 120,
            "comparison_ecosystems": 120,
            "target_users": 240,
            "markets": 120,
            "safety_goals": 500,
            "risk_scenarios": 500,
            "forbidden_inferences": 300,
            "evaluation_dimensions": 200,
            "validation_expectations": 500,
        }
        return _normalize_unique_strings(
            value,
            field_name=info.field_name,
            max_length=limits[info.field_name],
        )

    @field_validator("safety_domains", "authorized_signal_types", "deliverables")
    @classmethod
    def validate_enum_lists(cls, value: list[Any], info: Any) -> list[Any]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_ecosystem_roles(self) -> "ResearchBrief":
        targets = {value.casefold() for value in self.target_ecosystems}
        comparisons = {value.casefold() for value in self.comparison_ecosystems}
        overlap = targets & comparisons
        if overlap:
            raise ValueError("target_ecosystems and comparison_ecosystems must not overlap")
        return self

    @property
    def primary_market(self) -> str:
        return self.markets[0]

    @property
    def target_user_summary(self) -> str:
        return " / ".join(self.target_users)

    @property
    def safety_domain_summary(self) -> str:
        return " / ".join(domain.value for domain in self.safety_domains)


class ProjectCreate(BaseModel):
    brief: ResearchBrief
    model_selection: ModelSelection | None = None


class PendingDecision(BaseModel):
    decision_id: str
    gate: str
    allowed_actions: list[DecisionAction]


class Project(BaseModel):
    project_id: str
    status: ProjectStatus
    current_stage: str
    progress: int = Field(ge=0, le=100)
    brief: ResearchBrief
    model_selection: ModelSelection | None = None
    pending_decision: PendingDecision | None = None
    created_at: datetime
    updated_at: datetime


class DecisionCreate(BaseModel):
    decision_id: str
    action: DecisionAction
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(min_length=1, max_length=120)
    selected_concept_ids: list[str] = Field(default_factory=list)


class AgentRun(BaseModel):
    agent_run_id: str
    project_id: str
    task_id: str | None = None
    agent_type: str
    agent_name: str
    status: AgentRunStatus
    progress: int = Field(ge=0, le=100)
    quality_score: float = Field(default=0, ge=0, le=100)
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    model_id: str | None = None
    model_provider: str | None = None
    prompt_key: str | None = None
    prompt_version: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_microusd: int = Field(default=0, ge=0)


class ProjectEvent(BaseModel):
    event_id: str
    event_type: str
    project_id: str
    sequence_number: int = Field(ge=1)
    timestamp: datetime
    data: dict[str, Any]
    trace_id: str
