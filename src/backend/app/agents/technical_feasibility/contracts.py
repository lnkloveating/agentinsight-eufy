"""Strong contracts for evidence-bounded technical feasibility assessment."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Identifier = Annotated[str, Field(min_length=1, max_length=80)]
EvidenceId = Annotated[str, Field(min_length=1, max_length=80)]
Detail = Annotated[str, Field(min_length=1, max_length=2_000)]


def _unique(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


class TechnicalRequirementKind(StrEnum):
    CAPABILITY = "capability"
    DATA = "data"
    INTERFACE = "interface"
    DEPLOYMENT = "deployment"
    PERFORMANCE = "performance"
    PRIVACY = "privacy"
    PERMISSION = "permission"
    RESILIENCE = "resilience"
    HARDWARE = "hardware"


class TechnicalSupportStatus(StrEnum):
    SUPPORTED = "supported"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    CONFLICT = "conflict"


class TechnicalFeasibilityVerdict(StrEnum):
    DEMO_FEASIBLE = "demo_feasible"
    CONDITIONALLY_FEASIBLE = "conditionally_feasible"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_FEASIBLE = "not_feasible"


class TechnicalFeasibilityRunCreate(StrictModel):
    selected_opportunity_ids: list[Identifier] = Field(min_length=1, max_length=5)

    @field_validator("selected_opportunity_ids")
    @classmethod
    def _selected_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "selected_opportunity_ids")


class TechnicalRequirementModel(StrictModel):
    requirement_id: Identifier
    kind: TechnicalRequirementKind
    description: Detail
    status: TechnicalSupportStatus
    rationale: Detail
    evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=40)
    condition: str | None = Field(default=None, max_length=1_000)

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "requirement evidence_ids")

    @model_validator(mode="after")
    def _asserted_status_requires_evidence(self) -> TechnicalRequirementModel:
        if self.status is not TechnicalSupportStatus.UNKNOWN and not self.evidence_ids:
            raise ValueError("asserted technical requirement status requires evidence_ids")
        if self.status is TechnicalSupportStatus.CONDITIONAL and not self.condition:
            raise ValueError("conditional requirement requires a condition")
        return self


class TechnicalFeasibilityModelGap(StrictModel):
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    required_evidence_types: list[str] = Field(default_factory=list, max_length=20)
    affected_opportunity_ids: list[Identifier] = Field(default_factory=list, max_length=5)

    @field_validator("required_evidence_types", "affected_opportunity_ids")
    @classmethod
    def _lists_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "technical gap list")


class TechnicalFeasibilityModelAssessment(StrictModel):
    opportunity_id: Identifier
    architecture_summary: Detail
    requirements: list[TechnicalRequirementModel] = Field(min_length=1, max_length=60)
    demo_scope: Detail
    limitations: list[Detail] = Field(default_factory=list, max_length=30)
    failure_modes: list[Detail] = Field(default_factory=list, max_length=30)
    source_requirements: list[TechnicalFeasibilityModelGap] = Field(
        default_factory=list, max_length=30
    )

    @model_validator(mode="after")
    def _requirements_are_complete_and_unique(self) -> TechnicalFeasibilityModelAssessment:
        ids = [item.requirement_id for item in self.requirements]
        _unique(ids, "requirement_id")
        kinds = {item.kind for item in self.requirements}
        required_groups = (
            {TechnicalRequirementKind.DATA, TechnicalRequirementKind.INTERFACE},
            {TechnicalRequirementKind.DEPLOYMENT},
            {TechnicalRequirementKind.PERFORMANCE},
            {TechnicalRequirementKind.PRIVACY},
            {TechnicalRequirementKind.RESILIENCE},
        )
        if any(not kinds.intersection(group) for group in required_groups):
            raise ValueError(
                "technical assessment must cover data/interface, deployment, performance, "
                "privacy and resilience"
            )
        return self


class TechnicalFeasibilityModelOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=80)
    assessments: list[TechnicalFeasibilityModelAssessment] = Field(
        min_length=1, max_length=5
    )
    portfolio_gaps: list[TechnicalFeasibilityModelGap] = Field(
        default_factory=list, max_length=50
    )
    unknowns: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("summary_evidence_ids")
    @classmethod
    def _summary_evidence_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "summary_evidence_ids")

    @model_validator(mode="after")
    def _assessment_ids_unique(self) -> TechnicalFeasibilityModelOutput:
        ids = [item.opportunity_id for item in self.assessments]
        _unique(ids, "technical assessment opportunity_id")
        known = set(ids)
        for gap in self.portfolio_gaps:
            unknown = sorted(set(gap.affected_opportunity_ids) - known)
            if unknown:
                raise ValueError(f"technical gap references unknown opportunities: {unknown}")
        return self


class CapabilityFeasibilityAssessment(StrictModel):
    capability: str = Field(min_length=1, max_length=200)
    status: TechnicalSupportStatus
    matched_device_ids: list[Identifier] = Field(default_factory=list, max_length=50)
    evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=80)
    issues: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("matched_device_ids", "evidence_ids", "issues")
    @classmethod
    def _lists_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "capability assessment list")


class TechnicalFeasibilityGap(TechnicalFeasibilityModelGap):
    gap_id: Identifier


def technical_feasibility_gap_id(question: str, opportunity_ids: list[str]) -> str:
    canonical = json.dumps(
        {
            "question": question.casefold().strip(),
            "opportunity_ids": sorted(opportunity_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"gap_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


class TechnicalFeasibilityAssessment(StrictModel):
    opportunity_id: Identifier
    architecture_summary: Detail
    requirements: list[TechnicalRequirementModel] = Field(min_length=1, max_length=60)
    capability_assessments: list[CapabilityFeasibilityAssessment] = Field(
        default_factory=list, max_length=80
    )
    demo_scope: Detail
    limitations: list[Detail] = Field(default_factory=list, max_length=30)
    failure_modes: list[Detail] = Field(default_factory=list, max_length=30)
    verdict: TechnicalFeasibilityVerdict
    gate_issues: list[str] = Field(default_factory=list, max_length=60)
    source_requirements: list[TechnicalFeasibilityGap] = Field(
        default_factory=list, max_length=30
    )


class TechnicalFeasibilityCoverage(StrictModel):
    selected_opportunity_count: int = Field(ge=1, le=5)
    assessed_opportunity_count: int = Field(ge=0, le=5)
    demo_feasible_count: int = Field(ge=0, le=5)
    conditionally_feasible_count: int = Field(ge=0, le=5)
    insufficient_evidence_count: int = Field(ge=0, le=5)
    not_feasible_count: int = Field(ge=0, le=5)
    evidence_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    capability_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class TechnicalFeasibilityPayload(StrictModel):
    schema_name: Literal["technical_feasibility_portfolio"] = (
        "technical_feasibility_portfolio"
    )
    schema_version: Literal["1.0"] = "1.0"
    source_opportunity_artifact_id: Identifier
    selected_opportunity_ids: list[Identifier] = Field(min_length=1, max_length=5)
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=80)
    assessments: list[TechnicalFeasibilityAssessment] = Field(
        default_factory=list, max_length=5
    )
    portfolio_gaps: list[TechnicalFeasibilityGap] = Field(default_factory=list, max_length=50)
    coverage: TechnicalFeasibilityCoverage

    @model_validator(mode="after")
    def _content_is_consistent(self) -> TechnicalFeasibilityPayload:
        _unique(self.selected_opportunity_ids, "selected_opportunity_ids")
        assessed = [item.opportunity_id for item in self.assessments]
        _unique(assessed, "assessment opportunity_id")
        if set(assessed) != set(self.selected_opportunity_ids):
            raise ValueError("technical assessments must match selected opportunities")
        counts = {
            "demo_feasible_count": TechnicalFeasibilityVerdict.DEMO_FEASIBLE,
            "conditionally_feasible_count": TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE,
            "insufficient_evidence_count": TechnicalFeasibilityVerdict.INSUFFICIENT_EVIDENCE,
            "not_feasible_count": TechnicalFeasibilityVerdict.NOT_FEASIBLE,
        }
        if self.coverage.selected_opportunity_count != len(self.selected_opportunity_ids):
            raise ValueError("selected opportunity coverage count mismatch")
        if self.coverage.assessed_opportunity_count != len(self.assessments):
            raise ValueError("assessed opportunity coverage count mismatch")
        for field_name, verdict in counts.items():
            expected = sum(item.verdict is verdict for item in self.assessments)
            if getattr(self.coverage, field_name) != expected:
                raise ValueError(f"coverage {field_name} must be {expected}")
        return self


class TechnicalFeasibilityArtifact(StrictModel):
    artifact_id: Identifier
    task_id: Identifier
    artifact_type: Literal["technical_feasibility"] = "technical_feasibility"
    schema_version: Literal["1.0"] = "1.0"
    status: ResearchTaskStatus
    payload: TechnicalFeasibilityPayload
    evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=500)
    contradictions: list[str] = Field(default_factory=list, max_length=100)
    unknowns: list[str] = Field(default_factory=list, max_length=100)
    quality_score: float = Field(ge=0, le=100)
    errors: list[str] = Field(default_factory=list, max_length=100)

    def to_research_artifact(self) -> ResearchArtifact:
        return ResearchArtifact.model_validate(self.model_dump(mode="json"))

    @classmethod
    def from_research_artifact(
        cls, artifact: ResearchArtifact
    ) -> TechnicalFeasibilityArtifact:
        return cls.model_validate(artifact.model_dump(mode="json"))
