"""竞品候选发现 Agent 的强类型输入、输出与 Gate 契约。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.application.runtime import StoredArtifact
from app.schemas.source_requirements import ProductReference, SourceRequirementAssessment
from app.workflows.contracts import ResearchTaskStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompetitorComparisonDimension(StrEnum):
    CATEGORY_FIT = "category_fit"
    USER_SEGMENT = "user_segment"
    USE_CASE = "use_case"
    FORM_FACTOR = "form_factor"
    FEATURE_SET = "feature_set"
    PRICE_TIER = "price_tier"
    CHANNEL_OVERLAP = "channel_overlap"


class CompetitorCandidateGateStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


class CompetitorCandidateDecisionAction(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"


class CompetitorDiscoveryRunCreate(StrictModel):
    search_discovery_run_ids: list[str] = Field(min_length=1, max_length=5)
    minimum_candidates: int = Field(default=3, ge=1, le=10)

    @field_validator("search_discovery_run_ids")
    @classmethod
    def run_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("search discovery run ids must be unique")
        return value


class CompetitorDiscoveryCandidateReference(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=40)
    search_discovery_run_id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=500)
    source_url: HttpUrl
    source_domain: str = Field(min_length=1, max_length=253)
    snippet: str = Field(max_length=1_000)
    search_score: float | None = Field(default=None, ge=0, le=1)


class CompetitorDiscoveryInputContext(StrictModel):
    target_products: list[ProductReference] = Field(min_length=1, max_length=20)
    search_discovery_run_ids: list[str] = Field(min_length=1, max_length=5)
    candidates: list[CompetitorDiscoveryCandidateReference] = Field(
        min_length=1, max_length=50
    )
    minimum_candidates: int = Field(ge=1, le=10)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CompetitorDiscoveryModelProposal(StrictModel):
    brand: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=160)
    variant: str | None = Field(default=None, min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=160)
    candidate_ids: list[str] = Field(min_length=1, max_length=20)
    comparison_dimensions: list[CompetitorComparisonDimension] = Field(
        min_length=1, max_length=7
    )
    reason: str = Field(min_length=1, max_length=1_500)
    confidence: float = Field(ge=0, le=1)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("brand", "model", "variant", "category", "reason", mode="before")
    @classmethod
    def strip_product_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def lists_are_unique(self) -> "CompetitorDiscoveryModelProposal":
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("proposal candidate ids must be unique")
        if len(self.comparison_dimensions) != len(set(self.comparison_dimensions)):
            raise ValueError("comparison dimensions must be unique")
        return self


class CompetitorDiscoveryExcludedCandidate(StrictModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=1_000)

    @field_validator("candidate_ids")
    @classmethod
    def candidate_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("excluded candidate ids must be unique")
        return value


class CompetitorDiscoveryGap(StrictModel):
    question: str = Field(min_length=1, max_length=1_000)
    reason: str = Field(min_length=1, max_length=1_000)
    recommended_query: str = Field(min_length=1, max_length=500)


class CompetitorDiscoveryModelOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=4_000)
    proposals: list[CompetitorDiscoveryModelProposal] = Field(
        default_factory=list, max_length=20
    )
    excluded_candidates: list[CompetitorDiscoveryExcludedCandidate] = Field(
        default_factory=list, max_length=50
    )
    research_gaps: list[CompetitorDiscoveryGap] = Field(default_factory=list, max_length=30)
    unknowns: list[str] = Field(default_factory=list, max_length=50)


class CompetitorDiscoveryProposal(CompetitorDiscoveryModelProposal):
    proposal_id: str = Field(min_length=1, max_length=40)


class CompetitorDiscoveryCoverage(StrictModel):
    input_candidate_count: int = Field(ge=0)
    accounted_candidate_count: int = Field(ge=0)
    proposal_count: int = Field(ge=0)
    exact_model_count: int = Field(ge=0)
    minimum_candidates: int = Field(ge=1, le=10)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CompetitorDiscoveryPayload(StrictModel):
    schema_name: str = "competitor_discovery"
    schema_version: str = "1.0"
    summary: str
    target_products: list[ProductReference]
    input_candidates: list[CompetitorDiscoveryCandidateReference]
    proposals: list[CompetitorDiscoveryProposal]
    excluded_candidates: list[CompetitorDiscoveryExcludedCandidate]
    research_gaps: list[CompetitorDiscoveryGap]
    coverage: CompetitorDiscoveryCoverage


class CompetitorCandidateDecisionCreate(StrictModel):
    action: CompetitorCandidateDecisionAction
    selected_proposal_ids: list[str] = Field(default_factory=list, max_length=20)
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2_000)

    @field_validator("actor", "reason", mode="before")
    @classmethod
    def strip_audit_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_selection(self) -> "CompetitorCandidateDecisionCreate":
        if len(self.selected_proposal_ids) != len(set(self.selected_proposal_ids)):
            raise ValueError("selected proposal ids must be unique")
        if self.action is CompetitorCandidateDecisionAction.CONFIRM:
            if not self.selected_proposal_ids:
                raise ValueError("confirm requires at least one selected proposal")
        elif self.selected_proposal_ids:
            raise ValueError("only confirm may include selected proposal ids")
        return self


class CompetitorCandidateDecision(StrictModel):
    decision_id: str
    project_id: str
    artifact_id: str
    action: CompetitorCandidateDecisionAction
    selected_proposal_ids: list[str]
    actor: str
    reason: str
    created_at: datetime


class CompetitorDiscoveryArtifact(StrictModel):
    artifact_id: str
    agent_run_id: str
    version: int = Field(ge=1)
    status: ResearchTaskStatus
    schema_version: str = "1.0"
    summary: str
    target_products: list[ProductReference]
    input_candidates: list[CompetitorDiscoveryCandidateReference]
    proposals: list[CompetitorDiscoveryProposal]
    excluded_candidates: list[CompetitorDiscoveryExcludedCandidate]
    research_gaps: list[CompetitorDiscoveryGap]
    unknowns: list[str]
    quality_score: float = Field(ge=0, le=100)
    coverage: CompetitorDiscoveryCoverage
    gate_status: CompetitorCandidateGateStatus
    decision: CompetitorCandidateDecision | None = None

    @classmethod
    def from_stored(
        cls,
        stored: StoredArtifact,
        *,
        decision: CompetitorCandidateDecision | None,
    ) -> "CompetitorDiscoveryArtifact":
        payload = CompetitorDiscoveryPayload.model_validate(stored.artifact.payload)
        gate_status = {
            None: CompetitorCandidateGateStatus.PENDING,
            CompetitorCandidateDecisionAction.CONFIRM: (
                CompetitorCandidateGateStatus.CONFIRMED
            ),
            CompetitorCandidateDecisionAction.REJECT: CompetitorCandidateGateStatus.REJECTED,
            CompetitorCandidateDecisionAction.REQUEST_REVISION: (
                CompetitorCandidateGateStatus.REVISION_REQUESTED
            ),
        }[decision.action if decision is not None else None]
        return cls(
            artifact_id=stored.artifact.artifact_id,
            agent_run_id=stored.agent_run_id,
            version=stored.version,
            status=stored.artifact.status,
            schema_version=payload.schema_version,
            summary=payload.summary,
            target_products=payload.target_products,
            input_candidates=payload.input_candidates,
            proposals=payload.proposals,
            excluded_candidates=payload.excluded_candidates,
            research_gaps=payload.research_gaps,
            unknowns=stored.artifact.unknowns,
            quality_score=stored.artifact.quality_score,
            coverage=payload.coverage,
            gate_status=gate_status,
            decision=decision,
        )


class CompetitorCandidateDecisionResult(StrictModel):
    artifact: CompetitorDiscoveryArtifact
    source_requirements: SourceRequirementAssessment
