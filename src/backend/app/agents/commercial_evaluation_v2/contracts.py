"""Evidence-bound contracts for ecosystem Commercial Evaluation v2."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus

Identifier = Annotated[str, Field(min_length=1, max_length=80)]
Detail = Annotated[str, Field(min_length=1, max_length=2_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unique(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


class CommercialConclusionStatus(StrEnum):
    SUPPORTED = "supported"
    CONDITIONAL = "conditional"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNSUPPORTED = "unsupported"


class CommercialRecommendation(StrEnum):
    RECOMMEND_FOR_VALIDATION = "recommend_for_validation"
    CONDITIONAL = "conditional"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    DO_NOT_RECOMMEND = "do_not_recommend"


class CommercialDimension(StrEnum):
    USER_VALUE = "user_value"
    BUSINESS_MODEL = "business_model"
    DELIVERY_OPERATIONS = "delivery_operations"
    TARGET_SEGMENT = "target_segment"
    WILLINGNESS_TO_PAY = "willingness_to_pay"
    REVENUE_MODEL = "revenue_model"
    COMPUTE_COST = "compute_cost"
    SUPPORT_COST = "support_cost"
    DEVICE_COMPATIBILITY_COST = "device_compatibility_cost"
    PRIVACY_COMPLIANCE_COST = "privacy_compliance_cost"
    PILOT_CONVERSION = "pilot_conversion"


class CommercialEvaluationRunCreate(StrictModel):
    opportunity_ids: list[Identifier] = Field(default_factory=list, max_length=5)

    @field_validator("opportunity_ids")
    @classmethod
    def _opportunity_ids_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "opportunity_ids")


class CommercialClaimIntent(StrictModel):
    claim: str = Field(min_length=1, max_length=1_500)
    status: CommercialConclusionStatus
    rationale: Detail
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "claim evidence_ids")


class CommercialDimensionIntent(StrictModel):
    status: CommercialConclusionStatus
    conclusion: Detail
    claims: list[CommercialClaimIntent] = Field(min_length=1, max_length=40)
    assumptions: list[str] = Field(default_factory=list, max_length=40)


class BusinessHypothesisIntent(StrictModel):
    hypothesis: str = Field(min_length=1, max_length=1_500)
    validation_method: str = Field(min_length=1, max_length=1_500)
    decision_metric: str = Field(min_length=1, max_length=500)
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "hypothesis evidence_ids")


class CommercialGapIntent(StrictModel):
    dimension: CommercialDimension
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    affected_opportunity_ids: list[Identifier] = Field(min_length=1, max_length=5)
    recommended_source_types: list[str] = Field(min_length=1, max_length=20)

    @field_validator("affected_opportunity_ids", "recommended_source_types")
    @classmethod
    def _gap_lists_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "commercial gap list")


class CommercialEvaluationModelOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    user_value: CommercialDimensionIntent
    business_model: CommercialDimensionIntent
    business_hypotheses: list[BusinessHypothesisIntent] = Field(
        default_factory=list, max_length=40
    )
    commercial_gaps: list[CommercialGapIntent] = Field(default_factory=list, max_length=100)
    unknowns: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("summary_evidence_ids")
    @classmethod
    def _summary_evidence_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "summary_evidence_ids")


class CommercialClaim(CommercialClaimIntent):
    claim_id: Identifier


class CommercialDimensionConclusion(StrictModel):
    status: CommercialConclusionStatus
    conclusion: Detail
    claims: list[CommercialClaim] = Field(min_length=1, max_length=40)
    assumptions: list[str] = Field(default_factory=list, max_length=40)


class DeliveryOperationsConclusion(StrictModel):
    status: CommercialConclusionStatus
    conclusion: Detail
    technical_artifact_id: Identifier
    verification_artifact_id: Identifier
    conditional_opportunity_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    failed_scenario_ids: list[Identifier] = Field(default_factory=list, max_length=500)
    prerequisites: list[str] = Field(default_factory=list, max_length=100)
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=500)


class CommercialGap(CommercialGapIntent):
    gap_id: Identifier


class CommercialEvaluationCoverage(StrictModel):
    opportunity_count: int = Field(ge=1, le=5)
    user_value_claim_count: int = Field(ge=1)
    business_claim_count: int = Field(ge=1)
    hypothesis_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    evidence_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CommercialEvaluationPayload(StrictModel):
    schema_name: Literal["commercial_evaluation_v2"] = "commercial_evaluation_v2"
    schema_version: Literal["2.0"] = "2.0"
    source_opportunity_artifact_id: Identifier
    source_technical_artifact_id: Identifier
    source_verification_artifact_id: Identifier
    opportunity_ids: list[Identifier] = Field(min_length=1, max_length=5)
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    user_value: CommercialDimensionConclusion
    business_model: CommercialDimensionConclusion
    delivery_operations: DeliveryOperationsConclusion
    business_hypotheses: list[BusinessHypothesisIntent] = Field(
        default_factory=list, max_length=40
    )
    commercial_gaps: list[CommercialGap] = Field(default_factory=list, max_length=100)
    recommendation: CommercialRecommendation
    recommendation_reason: Detail
    coverage: CommercialEvaluationCoverage

    @model_validator(mode="after")
    def _opportunities_unique(self) -> CommercialEvaluationPayload:
        _unique(self.opportunity_ids, "opportunity_ids")
        return self


class CommercialEvaluationArtifact(StrictModel):
    artifact_id: Identifier
    task_id: Identifier
    artifact_type: Literal["commercial_evaluation"] = "commercial_evaluation"
    schema_version: Literal["2.0"] = "2.0"
    status: ResearchTaskStatus
    payload: CommercialEvaluationPayload
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=500)
    contradictions: list[str] = Field(default_factory=list, max_length=100)
    unknowns: list[str] = Field(default_factory=list, max_length=100)
    quality_score: float = Field(ge=0, le=100)
    errors: list[str] = Field(default_factory=list, max_length=100)

    def to_research_artifact(self) -> ResearchArtifact:
        return ResearchArtifact.model_validate(self.model_dump(mode="json"))

    @classmethod
    def from_research_artifact(
        cls, artifact: ResearchArtifact
    ) -> CommercialEvaluationArtifact:
        return cls.model_validate(artifact.model_dump(mode="json"))


def commercial_claim_id(dimension: str, claim: str, evidence_ids: list[str]) -> str:
    return _stable_id(
        "claim", {"dimension": dimension, "claim": claim, "evidence_ids": evidence_ids}
    )


def commercial_gap_id(question: str, opportunity_ids: list[str]) -> str:
    return _stable_id(
        "gap",
        {"question": question.casefold().strip(), "opportunity_ids": opportunity_ids},
    )


def _stable_id(prefix: str, value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"{prefix}_{digest[:16]}"
