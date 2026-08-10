"""Strong contracts for evidence-bounded future product opportunities."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.innovation import EventUnderstanding, ProblemDefinition, TargetUser
from app.workflows.contracts import ResearchArtifact, ResearchHandoffStatus, ResearchTaskStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductTechnicalGap(StrictModel):
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    required_evidence_types: list[str] = Field(default_factory=list, max_length=20)
    affected_candidate_ids: list[str] = Field(default_factory=list, max_length=5)


class ProductTechnicalAssessment(StrictModel):
    data_requirements: list[str] = Field(min_length=1, max_length=20)
    required_capabilities: list[str] = Field(min_length=1, max_length=20)
    privacy_constraints: list[str] = Field(default_factory=list, max_length=20)
    feasibility_summary: str = Field(min_length=1, max_length=2_000)
    demo_validation_plan: str = Field(min_length=1, max_length=2_000)


class ProductOpportunityModelCandidate(StrictModel):
    """Candidate semantics emitted by the model; gate fields are backend-owned."""

    candidate_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    target_user: TargetUser
    problem: ProblemDefinition
    event_understanding: EventUnderstanding
    competitor_gap_ids: list[str] = Field(default_factory=list, max_length=50)
    technical_assessment: ProductTechnicalAssessment
    evidence_ids: list[str] = Field(min_length=2, max_length=60)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> ProductOpportunityModelCandidate:
        for field_name in ("competitor_gap_ids", "evidence_ids"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class ProductTechnicalModelOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[str] = Field(default_factory=list, max_length=60)
    candidates: list[ProductOpportunityModelCandidate] = Field(default_factory=list, max_length=5)
    portfolio_gaps: list[ProductTechnicalGap] = Field(default_factory=list, max_length=30)
    unknowns: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("summary_evidence_ids")
    @classmethod
    def summary_evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("summary_evidence_ids must be unique")
        return value

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> ProductTechnicalModelOutput:
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id must be unique")
        return self

    def cited_evidence_ids(self) -> set[str]:
        return {
            *self.summary_evidence_ids,
            *(
                evidence_id
                for candidate in self.candidates
                for evidence_id in candidate.evidence_ids
            ),
        }


class CandidateGateStatus(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


class ProductOpportunityCandidate(ProductOpportunityModelCandidate):
    gate_status: CandidateGateStatus
    gate_issues: list[str] = Field(default_factory=list)


class ProductTechnicalCoverage(StrictModel):
    target_candidate_count: Literal[3] = 3
    maximum_candidate_count: Literal[5] = 5
    generated_candidate_count: int = Field(ge=0, le=5)
    advancing_candidate_count: int = Field(ge=0, le=5)
    cited_user_evidence_count: int = Field(ge=0)
    cited_competitor_evidence_count: int = Field(ge=0)
    evidence_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    handoff_status: ResearchHandoffStatus


class ProductTechnicalPayload(StrictModel):
    schema_name: str = "product_technical_opportunity_portfolio"
    schema_version: str = "1.0"
    summary: str
    summary_evidence_ids: list[str]
    candidates: list[ProductOpportunityCandidate] = Field(default_factory=list, max_length=5)
    portfolio_gaps: list[ProductTechnicalGap] = Field(default_factory=list, max_length=30)
    coverage: ProductTechnicalCoverage


class ProductTechnicalArtifact(StrictModel):
    artifact_id: str
    task_id: str
    artifact_type: str
    schema_version: str
    status: ResearchTaskStatus
    payload: ProductTechnicalPayload
    evidence_ids: list[str]
    contradictions: list[str]
    unknowns: list[str]
    quality_score: float = Field(ge=0, le=100)
    errors: list[str]

    @classmethod
    def from_research_artifact(cls, artifact: ResearchArtifact) -> ProductTechnicalArtifact:
        return cls.model_validate(artifact.model_dump(mode="json"))

    def to_research_artifact(self) -> ResearchArtifact:
        return ResearchArtifact.model_validate(self.model_dump(mode="json"))
