"""Strong contracts for evidence-bound Red Team Policy Revision v2."""

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


class RedTeamAttackDimension(StrEnum):
    EVIDENCE_INTEGRITY = "evidence_integrity"
    TECHNICAL_FEASIBILITY = "technical_feasibility"
    SAFETY_FAILURE = "safety_failure"
    PRIVACY_CONSENT = "privacy_consent"
    FALSE_POSITIVE_NEGATIVE = "false_positive_negative"
    OFFLINE_DEGRADATION = "offline_degradation"
    INTERVENTION_AUTHORITY = "intervention_authority"
    COMMERCIAL_CLAIM = "commercial_claim"
    AI_NATIVE_DISTINCTION = "ai_native_distinction"
    USER_CHALLENGE = "user_challenge"


REQUIRED_AUTOMATED_DIMENSIONS = frozenset(RedTeamAttackDimension) - {
    RedTeamAttackDimension.USER_CHALLENGE
}


class RedTeamSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RedTeamVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    HUMAN_REVIEW = "human_review"
    REJECT = "reject"


class ChallengeResponseStatus(StrEnum):
    ANSWERED = "answered"
    PARTIALLY_ANSWERED = "partially_answered"
    UNRESOLVED = "unresolved"
    REQUIRES_HUMAN_DECISION = "requires_human_decision"


class RedTeamChallengeCreate(StrictModel):
    question: str = Field(min_length=1, max_length=2_000)
    actor: str = Field(min_length=1, max_length=120)
    target_artifact_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    target_policy_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    target_scenario_ids: list[Identifier] = Field(default_factory=list, max_length=50)

    @field_validator("target_artifact_ids", "target_policy_ids", "target_scenario_ids")
    @classmethod
    def _targets_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "challenge targets")


class RedTeamRunCreate(StrictModel):
    challenges: list[RedTeamChallengeCreate] = Field(default_factory=list, max_length=20)


class RedTeamChallenge(RedTeamChallengeCreate):
    challenge_id: Identifier


class RedTeamFindingIntent(StrictModel):
    dimension: RedTeamAttackDimension
    severity: RedTeamSeverity
    title: str = Field(min_length=1, max_length=500)
    description: Detail
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    affected_artifact_ids: list[Identifier] = Field(min_length=1, max_length=20)
    affected_agent_types: list[Identifier] = Field(min_length=1, max_length=7)
    affected_opportunity_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    affected_policy_ids: list[Identifier] = Field(default_factory=list, max_length=50)
    affected_scenario_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    required_actions: list[str] = Field(default_factory=list, max_length=50)
    requires_source_recovery: bool = False
    requires_human_decision: bool = False
    irreducible: bool = False

    @field_validator(
        "evidence_ids",
        "affected_artifact_ids",
        "affected_agent_types",
        "affected_opportunity_ids",
        "affected_policy_ids",
        "affected_scenario_ids",
        "required_actions",
    )
    @classmethod
    def _lists_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "finding values")

    @model_validator(mode="after")
    def _action_is_explicit(self) -> RedTeamFindingIntent:
        if (
            self.severity in {RedTeamSeverity.HIGH, RedTeamSeverity.CRITICAL}
            and not self.required_actions
            and not self.requires_source_recovery
            and not self.requires_human_decision
            and not self.irreducible
        ):
            raise ValueError("high-severity findings require an explicit next action")
        return self


class RedTeamGapIntent(StrictModel):
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    severity: RedTeamSeverity
    dimension: RedTeamAttackDimension
    recommended_source_types: list[str] = Field(min_length=1, max_length=20)
    required_evidence_types: list[str] = Field(min_length=1, max_length=20)
    affected_agent_types: list[Identifier] = Field(min_length=1, max_length=7)
    affected_opportunity_ids: list[Identifier] = Field(default_factory=list, max_length=5)

    @field_validator(
        "recommended_source_types",
        "required_evidence_types",
        "affected_agent_types",
        "affected_opportunity_ids",
    )
    @classmethod
    def _lists_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "red-team gap values")


class RedTeamChallengeResponseIntent(StrictModel):
    challenge_id: Identifier
    status: ChallengeResponseStatus
    answer: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    related_finding_indexes: list[int] = Field(default_factory=list, max_length=50)

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "challenge evidence_ids")


class RedTeamFallbackPlan(StrictModel):
    safe_scope: Detail
    blocked_reason: Detail
    reentry_conditions: list[str] = Field(min_length=1, max_length=50)
    validation_demo: Detail

    @field_validator("reentry_conditions")
    @classmethod
    def _conditions_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "fallback reentry_conditions")


class RedTeamModelOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    attacked_dimensions: list[RedTeamAttackDimension] = Field(min_length=9, max_length=10)
    findings: list[RedTeamFindingIntent] = Field(default_factory=list, max_length=200)
    challenge_responses: list[RedTeamChallengeResponseIntent] = Field(
        default_factory=list, max_length=20
    )
    red_team_gaps: list[RedTeamGapIntent] = Field(default_factory=list, max_length=100)
    fallback_plan: RedTeamFallbackPlan | None = None
    unknowns: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("summary_evidence_ids", "attacked_dimensions")
    @classmethod
    def _top_level_unique(cls, value: list[object]) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError("red-team top-level values must be unique")
        return value


class RedTeamFinding(RedTeamFindingIntent):
    finding_id: Identifier


class RedTeamChallengeResponse(StrictModel):
    challenge_id: Identifier
    question: str = Field(min_length=1, max_length=2_000)
    status: ChallengeResponseStatus
    answer: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    related_finding_ids: list[Identifier] = Field(default_factory=list, max_length=50)


class RedTeamGap(RedTeamGapIntent):
    gap_id: Identifier


class RedTeamRevisionRequest(StrictModel):
    revision_id: Identifier
    finding_ids: list[Identifier] = Field(min_length=1, max_length=100)
    affected_agent_types: list[Identifier] = Field(min_length=1, max_length=7)
    affected_task_ids: list[Identifier] = Field(min_length=1, max_length=20)
    required_actions: list[str] = Field(min_length=1, max_length=100)
    resume_from_agent: Identifier
    reason: Detail


class RedTeamVersionDiff(StrictModel):
    previous_artifact_id: Identifier | None = None
    added_finding_ids: list[Identifier] = Field(default_factory=list, max_length=200)
    resolved_finding_ids: list[Identifier] = Field(default_factory=list, max_length=200)
    unchanged_finding_ids: list[Identifier] = Field(default_factory=list, max_length=200)


class RedTeamCoverage(StrictModel):
    required_dimension_count: int = Field(ge=9, le=9)
    attacked_dimension_count: int = Field(ge=0, le=10)
    finding_count: int = Field(ge=0, le=200)
    challenge_count: int = Field(ge=0, le=20)
    unresolved_challenge_count: int = Field(ge=0, le=20)
    evidence_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RedTeamPayload(StrictModel):
    schema_name: Literal["red_team_policy_revision"] = "red_team_policy_revision"
    schema_version: Literal["2.0"] = "2.0"
    source_artifact_ids: dict[Identifier, Identifier] = Field(min_length=7, max_length=7)
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    findings: list[RedTeamFinding] = Field(default_factory=list, max_length=200)
    challenge_responses: list[RedTeamChallengeResponse] = Field(default_factory=list, max_length=20)
    red_team_gaps: list[RedTeamGap] = Field(default_factory=list, max_length=100)
    revision_requests: list[RedTeamRevisionRequest] = Field(default_factory=list, max_length=20)
    fallback_plan: RedTeamFallbackPlan | None = None
    verdict: RedTeamVerdict
    verdict_reason: Detail
    version_diff: RedTeamVersionDiff
    coverage: RedTeamCoverage


class RedTeamArtifact(StrictModel):
    artifact_id: Identifier
    task_id: Identifier
    artifact_type: Literal["red_team"] = "red_team"
    schema_version: Literal["2.0"] = "2.0"
    status: ResearchTaskStatus
    payload: RedTeamPayload
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=1_000)
    contradictions: list[str] = Field(default_factory=list, max_length=200)
    unknowns: list[str] = Field(default_factory=list, max_length=200)
    quality_score: float = Field(ge=0, le=100)
    errors: list[str] = Field(default_factory=list, max_length=100)

    def to_research_artifact(self) -> ResearchArtifact:
        return ResearchArtifact.model_validate(self.model_dump(mode="json"))

    @classmethod
    def from_research_artifact(cls, artifact: ResearchArtifact) -> RedTeamArtifact:
        return cls.model_validate(artifact.model_dump(mode="json"))


def challenge_id(challenge: RedTeamChallengeCreate) -> str:
    return _stable_id("challenge", challenge.model_dump(mode="json"))


def finding_id(finding: RedTeamFindingIntent) -> str:
    return _stable_id(
        "finding",
        {
            "dimension": finding.dimension,
            "title": finding.title.casefold().strip(),
            "affected_artifact_ids": sorted(finding.affected_artifact_ids),
            "affected_policy_ids": sorted(finding.affected_policy_ids),
            "affected_scenario_ids": sorted(finding.affected_scenario_ids),
        },
    )


def red_team_gap_id(gap: RedTeamGapIntent) -> str:
    return _stable_id(
        "gap",
        {
            "question": gap.question.casefold().strip(),
            "dimension": gap.dimension,
            "affected_agent_types": sorted(gap.affected_agent_types),
            "affected_opportunity_ids": sorted(gap.affected_opportunity_ids),
        },
    )


def revision_id(finding_ids: list[str], affected_task_ids: list[str]) -> str:
    return _stable_id(
        "revision",
        {"finding_ids": sorted(finding_ids), "affected_task_ids": sorted(affected_task_ids)},
    )


def _stable_id(prefix: str, value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"{prefix}_{digest[:16]}"
