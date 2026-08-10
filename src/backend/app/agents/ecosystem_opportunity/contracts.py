"""Strong contracts for evidence-bounded ecosystem-level solution opportunities.

The models split what a model is *allowed to emit* from what the backend *owns*:

* ``*ModelCandidate`` / ``*ModelGap`` / ``*ModelOutput`` describe model-authored fields only.
  They must never contain ``gate_status`` or any deterministic verdict, which ``extra="forbid"``
  enforces structurally.
* ``EcosystemOpportunityCandidate`` / ``EcosystemOpportunityGap`` add backend-owned fields
  (``gate_status``, ``gate_issues``, deterministic ``gap_id``).

This branch only defines and structurally validates the contract. Semantic AI-native judgement,
device-capability grounding and real Agent execution are deferred to later branches.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.innovation import ProblemDefinition, TargetUser
from app.workflows.contracts import ResearchArtifact, ResearchHandoffStatus, ResearchTaskStatus


class StrictModel(BaseModel):
    # ``protected_namespaces=()`` keeps the spec-mandated ``model_responsibilities`` field on
    # ``AINativeCase`` from colliding with Pydantic's reserved ``model_`` namespace.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


def _require_unique(value: list[str], field_name: str) -> list[str]:
    if len(value) != len(set(value)):
        raise ValueError(f"{field_name} must be unique")
    return value


class SolutionScope(StrEnum):
    DEVICE_FEATURE = "device_feature"
    DEVICE_PRODUCT = "device_product"
    ECOSYSTEM_SERVICE = "ecosystem_service"


class EcosystemDeploymentTarget(StrEnum):
    DEVICE = "device"
    HOMEBASE = "homebase"
    CLOUD = "cloud"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class EcosystemScenarioType(StrEnum):
    NORMAL = "normal"
    BOUNDARY = "boundary"
    FAILURE = "failure"
    ADVERSARIAL = "adversarial"


class DeviceRoleType(StrEnum):
    """Roles are expressed by function, never by a concrete eufy model name."""

    PRIMARY_PERCEPTION = "primary_perception"
    CONTEXT_SENSOR = "context_sensor"
    LOCAL_REASONING_HUB = "local_reasoning_hub"
    USER_APPROVAL_INTERFACE = "user_approval_interface"
    ACTION_DEVICE = "action_device"


class EcosystemGateStatus(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


class RequiredDeviceRole(StrictModel):
    role_id: str = Field(min_length=1, max_length=80)
    role_type: DeviceRoleType
    description: str = Field(min_length=1, max_length=2_000)
    required_capabilities: list[str] = Field(default_factory=list, max_length=20)
    optional: bool = False
    evidence_ids: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("required_capabilities", "evidence_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "required_device_role list")


class CrossDeviceInformationFlow(StrictModel):
    flow_id: str = Field(min_length=1, max_length=80)
    from_role_id: str = Field(min_length=1, max_length=80)
    to_role_id: str = Field(min_length=1, max_length=80)
    data_type: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=1_000)
    privacy_constraints: list[str] = Field(default_factory=list, max_length=20)
    fallback: str = Field(min_length=1, max_length=1_000)

    @field_validator("privacy_constraints")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "privacy_constraints")


class EcosystemBlueprint(StrictModel):
    """Describes *what roles and capabilities the solution requires*.

    It never asserts that a specific real eufy model provides a capability; grounded device
    capabilities come from the evidence-backed Device Capability Graph in a later branch.
    """

    required_device_roles: list[RequiredDeviceRole] = Field(min_length=1, max_length=20)
    required_capabilities: list[str] = Field(default_factory=list, max_length=40)
    cross_device_information_flows: list[CrossDeviceInformationFlow] = Field(
        default_factory=list, max_length=40
    )
    deployment_target: EcosystemDeploymentTarget
    privacy_boundary: str = Field(min_length=1, max_length=2_000)
    permission_boundary: str = Field(min_length=1, max_length=2_000)
    offline_behavior: str = Field(min_length=1, max_length=2_000)
    fallback_behavior: str = Field(min_length=1, max_length=2_000)
    known_blind_spots: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("required_capabilities", "known_blind_spots")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "ecosystem_blueprint list")

    @model_validator(mode="after")
    def _roles_and_flows_are_consistent(self) -> EcosystemBlueprint:
        role_ids = [role.role_id for role in self.required_device_roles]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("required_device_roles must use unique role_id")
        flow_ids = [flow.flow_id for flow in self.cross_device_information_flows]
        if len(flow_ids) != len(set(flow_ids)):
            raise ValueError("cross_device_information_flows must use unique flow_id")
        known_roles = set(role_ids)
        for flow in self.cross_device_information_flows:
            unknown = sorted({flow.from_role_id, flow.to_role_id} - known_roles)
            if unknown:
                raise ValueError(
                    f"information flow {flow.flow_id} references unknown role_id {unknown}"
                )
        return self


class AIRemovalTest(StrictModel):
    core_value_survives_without_ai: bool
    rationale: str = Field(min_length=1, max_length=2_000)
    lost_capabilities_without_ai: list[str] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("lost_capabilities_without_ai", "evidence_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "ai_removal_test list")


class AINativeCase(StrictModel):
    open_ended_goal: str = Field(min_length=1, max_length=2_000)
    why_fixed_rules_are_insufficient: str = Field(min_length=1, max_length=2_000)
    model_responsibilities: list[str] = Field(min_length=1, max_length=20)
    deterministic_responsibilities: list[str] = Field(min_length=1, max_length=20)
    ai_removal_test: AIRemovalTest
    learning_or_revision_loop: list[str] = Field(default_factory=list, max_length=20)
    safety_constraints: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "model_responsibilities",
        "deterministic_responsibilities",
        "learning_or_revision_loop",
        "safety_constraints",
    )
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "ai_native_case list")


class EcosystemValidationPlan(StrictModel):
    """Declares *how* the opportunity should be validated; it runs no simulation here."""

    validation_goal: str = Field(min_length=1, max_length=2_000)
    required_scenario_types: list[EcosystemScenarioType] = Field(min_length=1, max_length=4)
    success_conditions: list[str] = Field(min_length=1, max_length=20)
    failure_conditions: list[str] = Field(min_length=1, max_length=20)
    required_data: list[str] = Field(default_factory=list, max_length=20)
    human_review_points: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("required_scenario_types")
    @classmethod
    def _unique_scenario_types(
        cls, value: list[EcosystemScenarioType]
    ) -> list[EcosystemScenarioType]:
        codes = [item.value for item in value]
        if len(codes) != len(set(codes)):
            raise ValueError("required_scenario_types must be unique")
        return value

    @field_validator(
        "success_conditions", "failure_conditions", "required_data", "human_review_points"
    )
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "validation_plan list")


class EcosystemOpportunityModelCandidate(StrictModel):
    """Candidate semantics the model is allowed to emit; gate fields are backend-owned."""

    opportunity_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    scope_level: SolutionScope
    target_user: TargetUser
    problem: ProblemDefinition
    safety_goal: str = Field(min_length=1, max_length=2_000)
    ecosystem_blueprint: EcosystemBlueprint
    ai_native_case: AINativeCase
    competitor_gap_ids: list[str] = Field(default_factory=list, max_length=50)
    technical_hypotheses: list[str] = Field(default_factory=list, max_length=20)
    commercial_hypotheses: list[str] = Field(default_factory=list, max_length=20)
    validation_plan: EcosystemValidationPlan
    evidence_ids: list[str] = Field(min_length=2, max_length=60)

    @model_validator(mode="after")
    def _identifiers_are_unique(self) -> EcosystemOpportunityModelCandidate:
        for field_name in (
            "competitor_gap_ids",
            "technical_hypotheses",
            "commercial_hypotheses",
            "evidence_ids",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class EcosystemOpportunityCandidate(EcosystemOpportunityModelCandidate):
    gate_status: EcosystemGateStatus
    gate_issues: list[str] = Field(default_factory=list, max_length=50)


class EcosystemOpportunityModelGap(StrictModel):
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    required_evidence_types: list[str] = Field(default_factory=list, max_length=20)
    affected_opportunity_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("required_evidence_types", "affected_opportunity_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "ecosystem_opportunity_gap list")


class EcosystemOpportunityGap(EcosystemOpportunityModelGap):
    gap_id: str = Field(min_length=1, max_length=80)


def ecosystem_opportunity_gap_id(question: str, opportunity_ids: list[str]) -> str:
    """Deterministic, stable gap id so the model never invents unstable identifiers."""

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


class EcosystemOpportunityModelOutput(StrictModel):
    """The structure the model is permitted to return before deterministic gating."""

    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[str] = Field(default_factory=list, max_length=60)
    opportunities: list[EcosystemOpportunityModelCandidate] = Field(
        default_factory=list, max_length=5
    )
    portfolio_gaps: list[EcosystemOpportunityModelGap] = Field(default_factory=list, max_length=30)
    unknowns: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("summary_evidence_ids")
    @classmethod
    def _summary_evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "summary_evidence_ids")

    @model_validator(mode="after")
    def _opportunity_ids_are_unique(self) -> EcosystemOpportunityModelOutput:
        ids = [item.opportunity_id for item in self.opportunities]
        if len(ids) != len(set(ids)):
            raise ValueError("opportunity_id must be unique")
        return self

    def cited_evidence_ids(self) -> set[str]:
        return {
            *self.summary_evidence_ids,
            *(
                evidence_id
                for opportunity in self.opportunities
                for evidence_id in opportunity.evidence_ids
            ),
        }


class EcosystemOpportunityCoverage(StrictModel):
    target_candidate_count: Literal[3] = 3
    maximum_candidate_count: Literal[5] = 5
    generated_candidate_count: int = Field(ge=0, le=5)
    advancing_candidate_count: int = Field(ge=0, le=5)
    ecosystem_service_count: int = Field(ge=0, le=5)
    cited_user_evidence_count: int = Field(ge=0)
    cited_competitor_evidence_count: int = Field(ge=0)
    evidence_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    handoff_status: ResearchHandoffStatus

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> EcosystemOpportunityCoverage:
        if self.advancing_candidate_count > self.generated_candidate_count:
            raise ValueError("advancing_candidate_count cannot exceed generated_candidate_count")
        if self.ecosystem_service_count > self.generated_candidate_count:
            raise ValueError("ecosystem_service_count cannot exceed generated_candidate_count")
        return self


class EcosystemOpportunityPayload(StrictModel):
    schema_name: str = "ecosystem_opportunity_portfolio"
    schema_version: str = "1.0"
    summary: str = Field(min_length=1, max_length=5_000)
    summary_evidence_ids: list[str] = Field(default_factory=list, max_length=60)
    opportunities: list[EcosystemOpportunityCandidate] = Field(default_factory=list, max_length=5)
    portfolio_gaps: list[EcosystemOpportunityGap] = Field(default_factory=list, max_length=30)
    coverage: EcosystemOpportunityCoverage

    @field_validator("summary_evidence_ids")
    @classmethod
    def _summary_evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "summary_evidence_ids")

    @model_validator(mode="after")
    def _opportunity_ids_are_unique(self) -> EcosystemOpportunityPayload:
        ids = [item.opportunity_id for item in self.opportunities]
        if len(ids) != len(set(ids)):
            raise ValueError("opportunity_id must be unique")
        return self


class EcosystemOpportunityArtifact(StrictModel):
    artifact_id: str
    task_id: str
    artifact_type: str
    schema_version: str
    status: ResearchTaskStatus
    payload: EcosystemOpportunityPayload
    evidence_ids: list[str]
    contradictions: list[str]
    unknowns: list[str]
    quality_score: float = Field(ge=0, le=100)
    errors: list[str]

    @classmethod
    def from_research_artifact(cls, artifact: ResearchArtifact) -> EcosystemOpportunityArtifact:
        data = artifact.model_dump(mode="json")
        payload = data.get("payload")
        if isinstance(payload, dict):
            gaps = payload.get("portfolio_gaps")
            if isinstance(gaps, list):
                for gap in gaps:
                    if isinstance(gap, dict) and not gap.get("gap_id"):
                        gap["gap_id"] = ecosystem_opportunity_gap_id(
                            str(gap.get("question", "")),
                            [str(item) for item in gap.get("affected_opportunity_ids", [])],
                        )
        return cls.model_validate(data)

    def to_research_artifact(self) -> ResearchArtifact:
        return ResearchArtifact.model_validate(self.model_dump(mode="json"))
