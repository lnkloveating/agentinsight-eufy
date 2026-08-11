"""Contracts for deterministic dry-run Security Policy verification."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.security_policy import (
    PolicyFallbackTrigger,
    PolicyRiskLevel,
)
from app.schemas.project import AllowedIntervention
from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus

Identifier = Annotated[str, Field(min_length=1, max_length=80)]
Scalar = bool | int | float | str | None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VerificationScenarioCategory(StrEnum):
    BASELINE = "baseline"
    RISK_RULE = "risk_rule"
    BOUNDARY = "boundary"
    DEVICE_OFFLINE = "device_offline"
    NETWORK_OFFLINE = "network_offline"
    SIGNAL_UNAVAILABLE = "signal_unavailable"
    UNCERTAIN_STATE = "uncertain_state"
    PERMISSION_DENIED = "permission_denied"
    ADVERSARIAL = "adversarial"
    USER_DEFINED = "user_defined"


class VerificationStatus(StrEnum):
    PASSED = "passed"
    CONDITIONALLY_PASSED = "conditionally_passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class ScenarioOrigin(StrEnum):
    GENERATED = "generated"
    USER = "user"


class ScenarioValueUpdate(StrictModel):
    at_seconds: int = Field(default=0, ge=0, le=604_800)
    reference: str = Field(pattern=r"^(state|signal):[a-z][a-z0-9_]{1,63}$")
    value: Scalar


class PolicyVerificationScenarioCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    policy_id: Identifier
    category: VerificationScenarioCategory = VerificationScenarioCategory.USER_DEFINED
    updates: list[ScenarioValueUpdate] = Field(default_factory=list, max_length=60)
    fallback_trigger: PolicyFallbackTrigger | None = None
    expected_risk_level: PolicyRiskLevel | None = None
    expected_action: AllowedIntervention | None = None
    rationale: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _has_observable_expectation(self) -> PolicyVerificationScenarioCreate:
        if not self.updates and self.fallback_trigger is None:
            raise ValueError("scenario requires updates or fallback_trigger")
        if self.expected_risk_level is None and self.expected_action is None:
            raise ValueError("scenario requires an expected risk or action")
        return self


class PolicyVerificationRunCreate(StrictModel):
    policy_artifact_id: Identifier | None = None
    scenarios: list[PolicyVerificationScenarioCreate] = Field(
        default_factory=list, max_length=30
    )


class PolicyVerificationScenario(PolicyVerificationScenarioCreate):
    scenario_id: Identifier
    origin: ScenarioOrigin


class ScenarioTraceStep(StrictModel):
    sequence: int = Field(ge=0, le=100)
    event: str = Field(min_length=1, max_length=500)
    risk_level: PolicyRiskLevel
    action: AllowedIntervention | None = None
    fired_rule_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    fallback_id: Identifier | None = None


class ScenarioAssertion(StrictModel):
    assertion: str = Field(min_length=1, max_length=500)
    passed: bool
    expected: str = Field(min_length=1, max_length=200)
    observed: str = Field(min_length=1, max_length=200)


class PolicyVerificationScenarioResult(StrictModel):
    scenario_id: Identifier
    policy_id: Identifier
    category: VerificationScenarioCategory
    status: VerificationStatus
    observed_risk_level: PolicyRiskLevel
    observed_action: AllowedIntervention | None = None
    fired_rule_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    fallback_id: Identifier | None = None
    assertions: list[ScenarioAssertion] = Field(min_length=1, max_length=20)
    trace: list[ScenarioTraceStep] = Field(min_length=1, max_length=100)
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)


class PolicyVerificationGap(StrictModel):
    gap_id: Identifier
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    affected_policy_ids: list[Identifier] = Field(min_length=1, max_length=5)
    affected_scenario_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    recommended_source_types: list[str] = Field(default_factory=list, max_length=20)


class PolicyVerificationCoverage(StrictModel):
    policy_count: int = Field(ge=1, le=5)
    scenario_count: int = Field(ge=1, le=500)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    generated_count: int = Field(ge=1)
    user_defined_count: int = Field(ge=0)
    fallback_types_covered: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def _counts_match(self) -> PolicyVerificationCoverage:
        if self.passed_count + self.failed_count + self.inconclusive_count != self.scenario_count:
            raise ValueError("scenario result counts must match scenario_count")
        if self.generated_count + self.user_defined_count != self.scenario_count:
            raise ValueError("scenario origin counts must match scenario_count")
        return self


class PolicyVerificationPayload(StrictModel):
    schema_name: Literal["security_policy_verification"] = "security_policy_verification"
    schema_version: Literal["1.0"] = "1.0"
    source_policy_artifact_id: Identifier
    source_policy_versions: dict[Identifier, int] = Field(min_length=1, max_length=5)
    verification_status: VerificationStatus
    recommendation: str = Field(min_length=1, max_length=2_000)
    scenarios: list[PolicyVerificationScenario] = Field(min_length=1, max_length=500)
    results: list[PolicyVerificationScenarioResult] = Field(min_length=1, max_length=500)
    validation_gaps: list[PolicyVerificationGap] = Field(default_factory=list, max_length=100)
    coverage: PolicyVerificationCoverage

    @model_validator(mode="after")
    def _scenarios_match_results(self) -> PolicyVerificationPayload:
        scenario_ids = [item.scenario_id for item in self.scenarios]
        result_ids = [item.scenario_id for item in self.results]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario IDs must be unique")
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("scenario result IDs must be unique")
        if set(scenario_ids) != set(result_ids):
            raise ValueError("every scenario requires exactly one result")
        return self


class PolicyVerificationArtifact(StrictModel):
    artifact_id: Identifier
    task_id: Identifier
    artifact_type: Literal["policy_verification"] = "policy_verification"
    schema_version: Literal["1.0"] = "1.0"
    status: ResearchTaskStatus
    payload: PolicyVerificationPayload
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
    ) -> PolicyVerificationArtifact:
        return cls.model_validate(artifact.model_dump(mode="json"))


def verification_scenario_id(policy_id: str, category: str, value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{policy_id}|{category}|{canonical}".encode()).hexdigest()
    return f"scenario_{digest[:16]}"


def verification_gap_id(question: str, policy_ids: list[str]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"question": question.casefold().strip(), "policy_ids": sorted(policy_ids)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return f"gap_{digest[:16]}"
