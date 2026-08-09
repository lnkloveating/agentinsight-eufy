"""Strong contracts for competitor synthesis and deterministic evidence audit."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SynthesisDimension(StrEnum):
    OFFICIAL_PRODUCT = "official_product"
    PRICE_CHANNEL = "price_channel"
    USER_REVIEW = "user_review"
    CROSS_DIMENSION = "cross_dimension"


class SynthesisGapSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HypothesisStatus(StrEnum):
    REQUIRES_PRODUCT_AGENT_VALIDATION = "requires_product_agent_validation"


class CitedSynthesisItem(StrictModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=60)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class ProductAssessmentPoint(CitedSynthesisItem):
    point_id: str = Field(min_length=1, max_length=100)
    dimension: SynthesisDimension
    statement: str = Field(min_length=1, max_length=2_000)
    explanation: str = Field(min_length=1, max_length=3_000)
    confidence: float = Field(ge=0, le=1)


class CompetitorProductProfile(StrictModel):
    scope_label: str = Field(min_length=1, max_length=240)
    strengths: list[ProductAssessmentPoint] = Field(default_factory=list, max_length=50)
    weaknesses: list[ProductAssessmentPoint] = Field(default_factory=list, max_length=50)
    tradeoffs: list[ProductAssessmentPoint] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def point_ids_are_unique(self) -> CompetitorProductProfile:
        point_ids = [
            point.point_id
            for point in [*self.strengths, *self.weaknesses, *self.tradeoffs]
        ]
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("point_id must be unique within a product profile")
        if not point_ids:
            raise ValueError("a product profile must contain at least one cited point")
        return self


class ComparativeInsight(CitedSynthesisItem):
    insight_id: str = Field(min_length=1, max_length=100)
    scope_labels: list[str] = Field(min_length=2, max_length=20)
    dimension: SynthesisDimension
    statement: str = Field(min_length=1, max_length=2_000)

    @field_validator("scope_labels")
    @classmethod
    def scope_labels_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("scope_labels must be unique")
        return value


class OpportunitySignal(CitedSynthesisItem):
    signal_id: str = Field(min_length=1, max_length=100)
    scope_labels: list[str] = Field(min_length=1, max_length=20)
    statement: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=3_000)
    validation_questions: list[str] = Field(min_length=1, max_length=20)
    hypothesis_status: HypothesisStatus = (
        HypothesisStatus.REQUIRES_PRODUCT_AGENT_VALIDATION
    )


class SynthesisResearchGap(StrictModel):
    scope_label: str = Field(min_length=1, max_length=240)
    dimension: SynthesisDimension
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    severity: SynthesisGapSeverity


class CompetitorSynthesisModelOutput(StrictModel):
    """Model semantics only; coverage, status and audit are backend-owned."""

    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[str] = Field(min_length=1, max_length=60)
    product_profiles: list[CompetitorProductProfile] = Field(
        default_factory=list, max_length=50
    )
    comparative_insights: list[ComparativeInsight] = Field(
        default_factory=list, max_length=100
    )
    opportunity_signals: list[OpportunitySignal] = Field(
        default_factory=list, max_length=100
    )
    research_gaps: list[SynthesisResearchGap] = Field(default_factory=list, max_length=100)
    unknowns: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> CompetitorSynthesisModelOutput:
        if len(self.summary_evidence_ids) != len(set(self.summary_evidence_ids)):
            raise ValueError("summary_evidence_ids must be unique")
        labels = [profile.scope_label for profile in self.product_profiles]
        if len(labels) != len(set(labels)):
            raise ValueError("scope_label must be unique")
        identifiers = [
            *(item.insight_id for item in self.comparative_insights),
            *(item.signal_id for item in self.opportunity_signals),
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("insight_id and signal_id must be unique")
        return self

    def cited_evidence_ids(self) -> set[str]:
        citations = set(self.summary_evidence_ids)
        for profile in self.product_profiles:
            for point in [*profile.strengths, *profile.weaknesses, *profile.tradeoffs]:
                citations.update(point.evidence_ids)
        for item in [*self.comparative_insights, *self.opportunity_signals]:
            citations.update(item.evidence_ids)
        return citations


class ProductDimensionCoverage(StrictModel):
    scope_label: str
    official_product_evidence_ids: list[str]
    price_channel_evidence_ids: list[str]
    user_review_evidence_ids: list[str]
    complete: bool


class CompetitorEvidenceAudit(StrictModel):
    status: str
    allowed_evidence_count: int = Field(ge=0)
    cited_evidence_count: int = Field(ge=0)
    specialist_output_count: int = Field(ge=0)
    requested_product_count: int = Field(ge=0)
    represented_product_count: int = Field(ge=0)
    complete_product_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    evidence_context_hash: str


class CompetitorSynthesisPayload(StrictModel):
    schema_name: str = "competitor_synthesis_intelligence"
    schema_version: str = "1.0"
    supervisor_mode: str = "a2a_specialists_then_evidence_bounded_synthesis"
    specialist_outputs: list[dict[str, object]]
    summary: str
    summary_evidence_ids: list[str]
    product_profiles: list[CompetitorProductProfile]
    comparative_insights: list[ComparativeInsight]
    opportunity_signals: list[OpportunitySignal]
    research_gaps: list[SynthesisResearchGap]
    coverage_matrix: list[ProductDimensionCoverage]
    evidence_audit: CompetitorEvidenceAudit
    synthesis_status: str
