"""用户研究 Agent 的强类型业务输出与公开 Artifact 契约。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CitedFinding(StrictModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=30)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class UserEventChain(CitedFinding):
    event: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1, max_length=1000)
    user_state: str = Field(min_length=1, max_length=1000)
    current_response: str = Field(min_length=1, max_length=1000)


class UserPainPoint(CitedFinding):
    pain_point_id: str = Field(min_length=1, max_length=80)
    user_expression: str = Field(min_length=1, max_length=1500)
    trigger_event: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1, max_length=1000)
    severity: FindingSeverity
    frequency_basis: str = Field(min_length=1, max_length=1000)
    current_workaround: str = Field(min_length=1, max_length=1000)
    solution_gap: str = Field(min_length=1, max_length=1500)
    confidence: float = Field(ge=0, le=1)


class UserUnmetNeed(CitedFinding):
    need_id: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=1500)
    desired_outcome: str = Field(min_length=1, max_length=1500)
    confidence: float = Field(ge=0, le=1)


class SampleBias(CitedFinding):
    description: str = Field(min_length=1, max_length=1500)
    impact: str = Field(min_length=1, max_length=1500)


class EvidenceContradiction(CitedFinding):
    statement: str = Field(min_length=1, max_length=1500)


class ResearchGap(StrictModel):
    question: str = Field(min_length=1, max_length=1500)
    reason: str = Field(min_length=1, max_length=1500)
    severity: FindingSeverity
    recommended_source_types: list[str] = Field(default_factory=list, max_length=20)


class UserResearchModelOutput(StrictModel):
    """模型只负责研究推理；状态、覆盖率与质量分由后端计算。"""

    summary: str = Field(min_length=1, max_length=4000)
    summary_evidence_ids: list[str] = Field(min_length=1, max_length=30)
    event_chains: list[UserEventChain] = Field(default_factory=list, max_length=20)
    pain_points: list[UserPainPoint] = Field(default_factory=list, max_length=20)
    unmet_needs: list[UserUnmetNeed] = Field(default_factory=list, max_length=20)
    sample_biases: list[SampleBias] = Field(default_factory=list, max_length=20)
    research_gaps: list[ResearchGap] = Field(default_factory=list, max_length=20)
    contradictions: list[EvidenceContradiction] = Field(
        default_factory=list, max_length=20
    )
    unknowns: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("summary_evidence_ids")
    @classmethod
    def summary_evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("summary_evidence_ids must be unique")
        return value

    def cited_evidence_ids(self) -> set[str]:
        citations = set(self.summary_evidence_ids)
        for collection in (
            self.event_chains,
            self.pain_points,
            self.unmet_needs,
            self.sample_biases,
            self.contradictions,
        ):
            for finding in collection:
                citations.update(finding.evidence_ids)
        return citations


class UserResearchEvidenceCoverage(StrictModel):
    available_evidence_count: int = Field(ge=0)
    included_evidence_count: int = Field(ge=0)
    cited_evidence_count: int = Field(ge=0)
    independent_domain_count: int = Field(ge=0)
    user_opinion_evidence_count: int = Field(ge=0)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class UserResearchPayload(StrictModel):
    summary: str
    summary_evidence_ids: list[str]
    event_chains: list[UserEventChain]
    pain_points: list[UserPainPoint]
    unmet_needs: list[UserUnmetNeed]
    sample_biases: list[SampleBias]
    research_gaps: list[ResearchGap]
    evidence_coverage: UserResearchEvidenceCoverage


class UserResearchArtifact(StrictModel):
    artifact_id: str
    task_id: str
    artifact_type: str
    schema_version: str
    status: ResearchTaskStatus
    payload: UserResearchPayload
    evidence_ids: list[str]
    contradictions: list[str]
    unknowns: list[str]
    quality_score: float = Field(ge=0, le=100)
    errors: list[str]

    @classmethod
    def from_research_artifact(cls, artifact: ResearchArtifact) -> UserResearchArtifact:
        return cls.model_validate(artifact.model_dump(mode="json"))

    def to_research_artifact(self) -> ResearchArtifact:
        return ResearchArtifact.model_validate(self.model_dump(mode="json"))


def serialize_payload(payload: UserResearchPayload) -> dict[str, Any]:
    return payload.model_dump(mode="json")
