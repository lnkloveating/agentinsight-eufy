"""Strong contracts for model intent and deterministically compiled policy DSL."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.project import AllowedIntervention, AuthorizedSignalType
from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Identifier = Annotated[str, Field(min_length=1, max_length=80)]
Detail = Annotated[str, Field(min_length=1, max_length=2_000)]
Scalar = bool | int | float | str | None


def _unique(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


class PolicyRiskLevel(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNCERTAIN = "uncertain"


class PolicyValueType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    TEXT = "text"
    TIMESTAMP = "timestamp"
    DURATION_SECONDS = "duration_seconds"
    RISK_LEVEL = "risk_level"


class PolicyConditionOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class PolicyFallbackTrigger(StrEnum):
    SIGNAL_UNAVAILABLE = "signal_unavailable"
    DEVICE_OFFLINE = "device_offline"
    NETWORK_OFFLINE = "network_offline"
    UNCERTAIN_STATE = "uncertain_state"
    PERMISSION_DENIED = "permission_denied"


class PolicyCompilationStatus(StrEnum):
    COMPILED = "compiled"
    CONDITIONAL = "conditional"


class SecurityPolicyRunCreate(StrictModel):
    selected_opportunity_ids: list[Identifier] = Field(min_length=1, max_length=5)

    @field_validator("selected_opportunity_ids")
    @classmethod
    def _selected_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "selected_opportunity_ids")


class PolicyStateVariableIntent(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    value_type: PolicyValueType
    description: Detail
    initial_value: Scalar = None
    retention_seconds: int = Field(ge=0, le=2_592_000)


class PolicySignalIntent(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    signal_type: AuthorizedSignalType
    source_role_id: Identifier
    purpose: Detail
    freshness_seconds: int = Field(ge=1, le=86_400)
    required: bool = True


class PolicyConditionIntent(StrictModel):
    reference: str = Field(pattern=r"^(state|signal):[a-z][a-z0-9_]{1,63}$")
    operator: PolicyConditionOperator
    value: Scalar = None

    @model_validator(mode="after")
    def _value_matches_operator(self) -> PolicyConditionIntent:
        unary = {
            PolicyConditionOperator.EXISTS,
            PolicyConditionOperator.NOT_EXISTS,
            PolicyConditionOperator.CHANGED,
            PolicyConditionOperator.UNCHANGED,
        }
        if self.operator in unary and self.value is not None:
            raise ValueError("unary condition operators cannot contain value")
        if self.operator not in unary and self.value is None:
            raise ValueError("comparison condition operators require value")
        return self


class PolicyRuleIntent(StrictModel):
    description: Detail
    conditions: list[PolicyConditionIntent] = Field(min_length=1, max_length=20)
    require_all_conditions: bool = True
    minimum_duration_seconds: int = Field(default=0, ge=0, le=86_400)
    within_seconds: int | None = Field(default=None, ge=1, le=604_800)
    resulting_risk_level: PolicyRiskLevel
    rationale: Detail
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=40)

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "rule evidence_ids")


class PolicyInterventionIntent(StrictModel):
    minimum_risk_level: PolicyRiskLevel
    action: AllowedIntervention
    human_approval_required: bool
    cooldown_seconds: int = Field(default=0, ge=0, le=86_400)
    rationale: Detail


class PolicyIntent(StrictModel):
    opportunity_id: Identifier
    policy_name: str = Field(min_length=1, max_length=200)
    objective: Detail
    state_variables: list[PolicyStateVariableIntent] = Field(min_length=1, max_length=30)
    signal_requests: list[PolicySignalIntent] = Field(min_length=1, max_length=30)
    risk_rules: list[PolicyRuleIntent] = Field(min_length=1, max_length=60)
    intervention_ladder: list[PolicyInterventionIntent] = Field(
        min_length=1, max_length=20
    )
    assumptions: list[str] = Field(default_factory=list, max_length=40)
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _keys_are_unique(self) -> PolicyIntent:
        _unique([item.key for item in self.state_variables], "state variable keys")
        _unique([item.key for item in self.signal_requests], "signal request keys")
        _unique(
            [f"{item.minimum_risk_level}:{item.action}" for item in self.intervention_ladder],
            "intervention ladder entries",
        )
        _unique(self.evidence_ids, "policy evidence_ids")
        return self


class PolicyCompilationGapIntent(StrictModel):
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    affected_opportunity_ids: list[Identifier] = Field(min_length=1, max_length=5)

    @field_validator("affected_opportunity_ids")
    @classmethod
    def _affected_unique(cls, value: list[str]) -> list[str]:
        return _unique(value, "gap affected_opportunity_ids")


class SecurityPolicyModelOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    policies: list[PolicyIntent] = Field(min_length=1, max_length=5)
    compilation_gaps: list[PolicyCompilationGapIntent] = Field(
        default_factory=list, max_length=40
    )
    unknowns: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _policy_ids_are_unique(self) -> SecurityPolicyModelOutput:
        _unique([item.opportunity_id for item in self.policies], "policy opportunity_ids")
        _unique(self.summary_evidence_ids, "summary_evidence_ids")
        known = {item.opportunity_id for item in self.policies}
        for gap in self.compilation_gaps:
            unknown = sorted(set(gap.affected_opportunity_ids) - known)
            if unknown:
                raise ValueError(f"compilation gap references unknown policies: {unknown}")
        return self


class CompiledPolicyStateVariable(PolicyStateVariableIntent):
    state_id: Identifier


class CompiledPolicySignal(PolicySignalIntent):
    signal_id: Identifier


class CompiledPolicyRule(PolicyRuleIntent):
    rule_id: Identifier


class CompiledPolicyIntervention(PolicyInterventionIntent):
    intervention_id: Identifier


class CompiledPolicyFallback(StrictModel):
    fallback_id: Identifier
    trigger: PolicyFallbackTrigger
    action: AllowedIntervention
    human_approval_required: bool
    safe_state: str = Field(min_length=1, max_length=500)
    rationale: Detail


class CompiledPolicyInvariant(StrictModel):
    invariant_id: Identifier
    kind: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=1_000)


class PolicyCompilationGap(PolicyCompilationGapIntent):
    gap_id: Identifier


class CompiledSecurityPolicy(StrictModel):
    policy_id: Identifier
    policy_version: int = Field(ge=1)
    opportunity_id: Identifier
    policy_name: str = Field(min_length=1, max_length=200)
    objective: Detail
    execution_mode: Literal["dry_run"] = "dry_run"
    compilation_status: PolicyCompilationStatus
    state_variables: list[CompiledPolicyStateVariable] = Field(min_length=1, max_length=30)
    signal_requests: list[CompiledPolicySignal] = Field(min_length=1, max_length=30)
    risk_rules: list[CompiledPolicyRule] = Field(min_length=1, max_length=60)
    intervention_ladder: list[CompiledPolicyIntervention] = Field(
        min_length=1, max_length=20
    )
    fallbacks: list[CompiledPolicyFallback] = Field(min_length=5, max_length=5)
    invariants: list[CompiledPolicyInvariant] = Field(min_length=4, max_length=100)
    technical_prerequisites: list[str] = Field(default_factory=list, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=40)
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=200)
    dsl_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SecurityPolicyVersionDiff(StrictModel):
    previous_artifact_id: Identifier | None = None
    added_policy_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    removed_policy_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    changed_policy_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    unchanged_policy_ids: list[Identifier] = Field(default_factory=list, max_length=5)


class SecurityPolicyCoverage(StrictModel):
    selected_opportunity_count: int = Field(ge=1, le=5)
    compiled_policy_count: int = Field(ge=1, le=5)
    conditional_policy_count: int = Field(ge=0, le=5)
    authorized_signal_type_count: int = Field(ge=1, le=8)
    allowed_intervention_count: int = Field(ge=1, le=6)
    evidence_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SecurityPolicyPayload(StrictModel):
    schema_name: Literal["security_policy_dsl_portfolio"] = (
        "security_policy_dsl_portfolio"
    )
    schema_version: Literal["1.0"] = "1.0"
    source_technical_artifact_id: Identifier
    source_opportunity_artifact_id: Identifier
    selected_opportunity_ids: list[Identifier] = Field(min_length=1, max_length=5)
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[Identifier] = Field(min_length=1, max_length=100)
    policies: list[CompiledSecurityPolicy] = Field(min_length=1, max_length=5)
    compilation_gaps: list[PolicyCompilationGap] = Field(default_factory=list, max_length=40)
    version_diff: SecurityPolicyVersionDiff
    coverage: SecurityPolicyCoverage

    @model_validator(mode="after")
    def _coverage_is_consistent(self) -> SecurityPolicyPayload:
        _unique(self.selected_opportunity_ids, "selected_opportunity_ids")
        policy_opportunity_ids = [item.opportunity_id for item in self.policies]
        _unique(policy_opportunity_ids, "compiled policy opportunity_ids")
        if set(policy_opportunity_ids) != set(self.selected_opportunity_ids):
            raise ValueError("compiled policies must match selected opportunities")
        if self.coverage.selected_opportunity_count != len(self.selected_opportunity_ids):
            raise ValueError("selected opportunity coverage count mismatch")
        if self.coverage.compiled_policy_count != len(self.policies):
            raise ValueError("compiled policy coverage count mismatch")
        conditional = sum(
            item.compilation_status is PolicyCompilationStatus.CONDITIONAL
            for item in self.policies
        )
        if self.coverage.conditional_policy_count != conditional:
            raise ValueError("conditional policy coverage count mismatch")
        return self


class SecurityPolicyArtifact(StrictModel):
    artifact_id: Identifier
    task_id: Identifier
    artifact_type: Literal["security_policy"] = "security_policy"
    schema_version: Literal["1.0"] = "1.0"
    status: ResearchTaskStatus
    payload: SecurityPolicyPayload
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=500)
    contradictions: list[str] = Field(default_factory=list, max_length=100)
    unknowns: list[str] = Field(default_factory=list, max_length=100)
    quality_score: float = Field(ge=0, le=100)
    errors: list[str] = Field(default_factory=list, max_length=100)

    def to_research_artifact(self) -> ResearchArtifact:
        return ResearchArtifact.model_validate(self.model_dump(mode="json"))

    @classmethod
    def from_research_artifact(cls, artifact: ResearchArtifact) -> SecurityPolicyArtifact:
        return cls.model_validate(artifact.model_dump(mode="json"))


def stable_policy_id(opportunity_id: str) -> str:
    digest = hashlib.sha256(opportunity_id.casefold().strip().encode("utf-8")).hexdigest()
    return f"policy_{digest[:16]}"


def stable_component_id(prefix: str, policy_id: str, value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{policy_id}|{canonical}".encode()).hexdigest()
    return f"{prefix}_{digest[:16]}"


def policy_gap_id(question: str, opportunity_ids: list[str]) -> str:
    return stable_component_id(
        "gap",
        "security_policy",
        {"question": question.casefold().strip(), "opportunity_ids": sorted(opportunity_ids)},
    )
