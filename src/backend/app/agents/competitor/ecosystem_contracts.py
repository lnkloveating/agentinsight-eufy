"""Evidence-bounded contracts for competitor ecosystem analysis v2."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application.runtime import StoredArtifact
from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EcosystemRole(StrEnum):
    TARGET = "target"
    COMPARISON = "comparison"


class EcosystemCapabilityDimension(StrEnum):
    SAFETY_GOAL_COVERAGE = "safety_goal_coverage"
    CROSS_DEVICE_ORCHESTRATION = "cross_device_orchestration"
    TEMPORAL_STATE_UNDERSTANDING = "temporal_state_understanding"
    ACTIVE_PERCEPTION = "active_perception"
    UNCERTAINTY_HANDLING = "uncertainty_handling"
    INTERVENTION_LADDER = "intervention_ladder"
    LOCAL_CLOUD_PARTITION = "local_cloud_partition"
    PRIVACY_AND_CONSENT = "privacy_and_consent"
    OFFLINE_FALLBACK = "offline_fallback"
    CAREGIVER_WORKFLOW = "caregiver_workflow"
    FAILURE_RECOVERY = "failure_recovery"
    BUSINESS_MODEL = "business_model"


class EcosystemCapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class EcosystemSourceDimension(StrEnum):
    OFFICIAL_PRODUCT = "official_product"
    PRICE_CHANNEL = "price_channel"
    USER_REVIEW = "user_review"


class EcosystemGapSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EcosystemCapabilityAssessment(StrictModel):
    assessment_id: str = Field(min_length=1, max_length=100)
    dimension: EcosystemCapabilityDimension
    status: EcosystemCapabilityStatus
    statement: str = Field(min_length=1, max_length=2_000)
    explanation: str = Field(min_length=1, max_length=3_000)
    source_dimensions: list[EcosystemSourceDimension] = Field(
        default_factory=list, max_length=3
    )
    evidence_ids: list[str] = Field(default_factory=list, max_length=60)
    confidence: float = Field(ge=0, le=1)
    unknown_reason: str | None = Field(default=None, min_length=1, max_length=1_500)

    @model_validator(mode="after")
    def validate_evidence_state(self) -> EcosystemCapabilityAssessment:
        if len(self.source_dimensions) != len(set(self.source_dimensions)):
            raise ValueError("source_dimensions must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        if self.status is EcosystemCapabilityStatus.UNKNOWN:
            if self.evidence_ids or self.source_dimensions:
                raise ValueError("unknown assessment cannot cite evidence or source dimensions")
            if self.unknown_reason is None:
                raise ValueError("unknown assessment requires unknown_reason")
        else:
            if not self.evidence_ids or not self.source_dimensions:
                raise ValueError("evidence-backed assessment requires citations and sources")
            if self.unknown_reason is not None:
                raise ValueError("evidence-backed assessment cannot include unknown_reason")
        return self


class CompetitorEcosystemProfile(StrictModel):
    ecosystem_label: str = Field(min_length=1, max_length=160)
    role: EcosystemRole
    product_scope_labels: list[str] = Field(default_factory=list, max_length=50)
    assessments: list[EcosystemCapabilityAssessment] = Field(
        min_length=1, max_length=12
    )

    @model_validator(mode="after")
    def validate_profile(self) -> CompetitorEcosystemProfile:
        if len(self.product_scope_labels) != len(set(self.product_scope_labels)):
            raise ValueError("product_scope_labels must be unique")
        dimensions = [item.dimension for item in self.assessments]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("ecosystem profile dimensions must be unique")
        return self


class EcosystemComparisonInsight(StrictModel):
    insight_id: str = Field(min_length=1, max_length=100)
    ecosystem_labels: list[str] = Field(min_length=2, max_length=30)
    dimension: EcosystemCapabilityDimension
    statement: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[str] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def values_are_unique(self) -> EcosystemComparisonInsight:
        if len(self.ecosystem_labels) != len(set(self.ecosystem_labels)):
            raise ValueError("ecosystem_labels must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        return self


class EcosystemOpportunitySignal(StrictModel):
    signal_id: str = Field(min_length=1, max_length=100)
    ecosystem_labels: list[str] = Field(min_length=1, max_length=30)
    gap_dimensions: list[EcosystemCapabilityDimension] = Field(min_length=1, max_length=12)
    statement: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=3_000)
    validation_questions: list[str] = Field(min_length=1, max_length=20)
    evidence_ids: list[str] = Field(min_length=1, max_length=60)
    hypothesis_status: Literal["requires_ecosystem_opportunity_validation"] = (
        "requires_ecosystem_opportunity_validation"
    )

    @model_validator(mode="after")
    def values_are_unique(self) -> EcosystemOpportunitySignal:
        for values, name in (
            (self.ecosystem_labels, "ecosystem_labels"),
            (self.gap_dimensions, "gap_dimensions"),
            (self.validation_questions, "validation_questions"),
            (self.evidence_ids, "evidence_ids"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be unique")
        return self


class EcosystemResearchGap(StrictModel):
    ecosystem_label: str = Field(min_length=1, max_length=160)
    dimension: EcosystemCapabilityDimension
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    severity: EcosystemGapSeverity


class CompetitorEcosystemModelOutput(StrictModel):
    """Model semantics only; scope, coverage and evidence lineage are backend-owned."""

    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[str] = Field(min_length=1, max_length=60)
    ecosystem_profiles: list[CompetitorEcosystemProfile] = Field(
        default_factory=list, max_length=30
    )
    comparison_insights: list[EcosystemComparisonInsight] = Field(
        default_factory=list, max_length=100
    )
    opportunity_signals: list[EcosystemOpportunitySignal] = Field(
        default_factory=list, max_length=100
    )
    research_gaps: list[EcosystemResearchGap] = Field(default_factory=list, max_length=360)
    unknowns: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> CompetitorEcosystemModelOutput:
        if len(self.summary_evidence_ids) != len(set(self.summary_evidence_ids)):
            raise ValueError("summary_evidence_ids must be unique")
        labels = [profile.ecosystem_label for profile in self.ecosystem_profiles]
        if len(labels) != len(set(labels)):
            raise ValueError("ecosystem_label must be unique")
        identifiers = [
            *(item.insight_id for item in self.comparison_insights),
            *(item.signal_id for item in self.opportunity_signals),
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("insight_id and signal_id must be unique")
        return self

    def cited_evidence_ids(self) -> set[str]:
        citations = set(self.summary_evidence_ids)
        for profile in self.ecosystem_profiles:
            for assessment in profile.assessments:
                citations.update(assessment.evidence_ids)
        for insight in self.comparison_insights:
            citations.update(insight.evidence_ids)
        for signal in self.opportunity_signals:
            citations.update(signal.evidence_ids)
        return citations


class EcosystemDiscoveryProjection(StrictModel):
    target_ecosystems: list[str]
    comparison_ecosystems: list[str]
    confirmed_product_scope: list[str]
    represented_ecosystems: list[str]
    unmapped_products: list[str]


class EcosystemDimensionCoverage(StrictModel):
    ecosystem_label: str
    dimension_statuses: dict[EcosystemCapabilityDimension, EcosystemCapabilityStatus]
    mapped_products: list[str]
    evidence_ids: list[str]
    evidence_backed_dimension_count: int = Field(ge=0, le=12)
    unknown_dimension_count: int = Field(ge=0, le=12)
    complete: bool


class CompetitorEcosystemEvidenceAudit(StrictModel):
    status: Literal["passed", "passed_with_gaps"]
    allowed_evidence_count: int = Field(ge=0)
    cited_evidence_count: int = Field(ge=0)
    specialist_output_count: int = Field(ge=0)
    requested_ecosystem_count: int = Field(ge=0)
    represented_ecosystem_count: int = Field(ge=0)
    mapped_product_count: int = Field(ge=0)
    evidence_backed_dimension_count: int = Field(ge=0)
    unknown_dimension_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    evidence_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CompetitorEcosystemPayload(StrictModel):
    schema_name: Literal["competitor_ecosystem_analysis"] = (
        "competitor_ecosystem_analysis"
    )
    schema_version: Literal["2.0"] = "2.0"
    supervisor_mode: Literal[
        "candidate_discovery_then_three_a2a_facts_then_ecosystem_synthesis"
    ] = "candidate_discovery_then_three_a2a_facts_then_ecosystem_synthesis"
    specialist_outputs: list[dict[str, object]]
    product_fact_synthesis: dict[str, object] | None = None
    discovery: EcosystemDiscoveryProjection
    summary: str
    summary_evidence_ids: list[str]
    ecosystem_profiles: list[CompetitorEcosystemProfile]
    comparison_insights: list[EcosystemComparisonInsight]
    opportunity_signals: list[EcosystemOpportunitySignal]
    research_gaps: list[EcosystemResearchGap]
    coverage_matrix: list[EcosystemDimensionCoverage]
    evidence_audit: CompetitorEcosystemEvidenceAudit
    synthesis_status: Literal["completed", "partial", "blocked"]


class CompetitorEcosystemArtifact(StrictModel):
    artifact_id: str
    agent_run_id: str
    version: int = Field(ge=1)
    status: ResearchTaskStatus
    schema_version: Literal["2.0"] = "2.0"
    payload: CompetitorEcosystemPayload
    evidence_ids: list[str]
    unknowns: list[str]
    quality_score: float = Field(ge=0, le=100)
    errors: list[str]

    @classmethod
    def from_research_artifact(
        cls,
        artifact: ResearchArtifact,
        *,
        agent_run_id: str,
        version: int,
    ) -> CompetitorEcosystemArtifact:
        return cls(
            artifact_id=artifact.artifact_id,
            agent_run_id=agent_run_id,
            version=version,
            status=artifact.status,
            payload=CompetitorEcosystemPayload.model_validate(artifact.payload),
            evidence_ids=artifact.evidence_ids,
            unknowns=artifact.unknowns,
            quality_score=artifact.quality_score,
            errors=artifact.errors,
        )

    @classmethod
    def from_stored(cls, stored: StoredArtifact) -> CompetitorEcosystemArtifact:
        return cls.from_research_artifact(
            stored.artifact,
            agent_run_id=stored.agent_run_id,
            version=stored.version,
        )
