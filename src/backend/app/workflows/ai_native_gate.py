"""Deterministic AI-native checks for ecosystem opportunity artifacts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.workflows.contracts import ResearchArtifact


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _SolutionScope(StrEnum):
    DEVICE_FEATURE = "device_feature"
    DEVICE_PRODUCT = "device_product"
    ECOSYSTEM_SERVICE = "ecosystem_service"


class _ScenarioType(StrEnum):
    NORMAL = "normal"
    BOUNDARY = "boundary"
    FAILURE = "failure"
    ADVERSARIAL = "adversarial"


class _RoleView(BaseModel):
    role_id: str
    optional: bool


class _FlowView(BaseModel):
    from_role_id: str
    to_role_id: str
    privacy_constraints: list[str]
    fallback: str


class _BlueprintView(BaseModel):
    required_device_roles: list[_RoleView]
    cross_device_information_flows: list[_FlowView]
    privacy_boundary: str
    permission_boundary: str
    offline_behavior: str
    fallback_behavior: str


class _AIRemovalView(BaseModel):
    core_value_survives_without_ai: bool
    rationale: str
    lost_capabilities_without_ai: list[str]


class _AINativeCaseView(BaseModel):
    model_responsibilities: list[str]
    deterministic_responsibilities: list[str]
    ai_removal_test: _AIRemovalView
    learning_or_revision_loop: list[str]
    safety_constraints: list[str]


class _ValidationPlanView(BaseModel):
    required_scenario_types: list[_ScenarioType]
    success_conditions: list[str]
    failure_conditions: list[str]
    human_review_points: list[str]


class _OpportunityView(BaseModel):
    opportunity_id: str
    scope_level: _SolutionScope
    gate_status: Literal["passed", "blocked"]
    ecosystem_blueprint: _BlueprintView
    ai_native_case: _AINativeCaseView
    validation_plan: _ValidationPlanView


class _GapView(BaseModel):
    gap_id: str
    question: str


class _OpportunityPayloadView(BaseModel):
    opportunities: list[_OpportunityView]
    portfolio_gaps: list[_GapView]


class AINativeCriterion(StrEnum):
    ECOSYSTEM_SCOPE = "ecosystem_scope"
    CROSS_DEVICE_LOOP = "cross_device_loop"
    AI_REMOVAL = "ai_removal"
    RESPONSIBILITY_SEPARATION = "responsibility_separation"
    REVISION_LOOP = "revision_loop"
    PRIVACY_AND_FALLBACK = "privacy_and_fallback"
    HUMAN_AUTHORIZATION = "human_authorization"
    PREDEPLOYMENT_VALIDATION = "predeployment_validation"


class AINativeCandidateStatus(StrEnum):
    BLOCKED = "blocked"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class AINativeCriterionResult(_StrictModel):
    criterion: AINativeCriterion
    passed: bool
    issues: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("issues")
    @classmethod
    def _issues_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("criterion issues must be unique")
        return value


class AINativeHumanReviewQuestion(_StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    opportunity_id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1_000)
    reason: str = Field(min_length=1, max_length=1_000)


class AINativeRevisionRequest(_StrictModel):
    revision_request_id: str = Field(min_length=1, max_length=80)
    affected_opportunity_ids: list[str] = Field(min_length=1, max_length=5)
    affected_task_ids: list[str] = Field(min_length=1, max_length=10)
    reasons: list[str] = Field(min_length=1, max_length=50)
    required_actions: list[str] = Field(min_length=1, max_length=50)

    @field_validator("affected_opportunity_ids", "affected_task_ids", "reasons", "required_actions")
    @classmethod
    def _lists_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("revision request lists must be unique")
        return value


class AINativeCandidateAssessment(_StrictModel):
    opportunity_id: str = Field(min_length=1, max_length=80)
    status: AINativeCandidateStatus
    criteria: list[AINativeCriterionResult] = Field(min_length=1, max_length=20)
    blocking_issues: list[str] = Field(default_factory=list, max_length=50)
    human_review_questions: list[AINativeHumanReviewQuestion] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def _status_matches_issues(self) -> AINativeCandidateAssessment:
        failed = [item for item in self.criteria if not item.passed]
        if self.status is AINativeCandidateStatus.BLOCKED and not failed:
            raise ValueError("blocked candidate must fail at least one criterion")
        if self.status is AINativeCandidateStatus.HUMAN_REVIEW_REQUIRED and failed:
            raise ValueError("human-review candidate cannot contain failed criteria")
        return self


class AINativeEcosystemGateResult(_StrictModel):
    schema_name: str = "ai_native_ecosystem_gate"
    schema_version: str = "1.0"
    source_artifact_id: str = Field(min_length=1, max_length=80)
    source_task_id: str = Field(min_length=1, max_length=80)
    ready_for_human_gate: bool
    eligible_opportunity_ids: list[str] = Field(default_factory=list, max_length=5)
    blocked_opportunity_ids: list[str] = Field(default_factory=list, max_length=5)
    assessments: list[AINativeCandidateAssessment] = Field(default_factory=list, max_length=5)
    revision_requests: list[AINativeRevisionRequest] = Field(default_factory=list, max_length=5)
    source_recovery_gap_ids: list[str] = Field(default_factory=list, max_length=30)
    source_recovery_questions: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _collections_are_consistent(self) -> AINativeEcosystemGateResult:
        assessed = {item.opportunity_id for item in self.assessments}
        eligible = set(self.eligible_opportunity_ids)
        blocked = set(self.blocked_opportunity_ids)
        if eligible & blocked:
            raise ValueError("eligible and blocked opportunities must not overlap")
        if assessed != eligible | blocked:
            raise ValueError("gate opportunity ids must match candidate assessments")
        if self.ready_for_human_gate != bool(eligible):
            raise ValueError("ready_for_human_gate must match eligible opportunities")
        return self


class AINativeEcosystemGate:
    """Own hard checks while leaving semantic AI-native judgement to a Human Gate."""

    def evaluate(self, artifact: ResearchArtifact) -> AINativeEcosystemGateResult:
        if artifact.artifact_type != "ecosystem_opportunity":
            raise ValueError("AI-native gate requires an ecosystem opportunity artifact")
        payload = _OpportunityPayloadView.model_validate(artifact.payload)
        assessments = [self._assess(candidate) for candidate in payload.opportunities]
        eligible = [
            item.opportunity_id
            for item in assessments
            if item.status is AINativeCandidateStatus.HUMAN_REVIEW_REQUIRED
        ]
        blocked = [
            item.opportunity_id
            for item in assessments
            if item.status is AINativeCandidateStatus.BLOCKED
        ]
        revisions = [
            self._revision(artifact.task_id, item)
            for item in assessments
            if item.status is AINativeCandidateStatus.BLOCKED
        ]
        gaps = payload.portfolio_gaps
        return AINativeEcosystemGateResult(
            source_artifact_id=artifact.artifact_id,
            source_task_id=artifact.task_id,
            ready_for_human_gate=bool(eligible),
            eligible_opportunity_ids=eligible,
            blocked_opportunity_ids=blocked,
            assessments=assessments,
            revision_requests=revisions,
            source_recovery_gap_ids=list(dict.fromkeys(item.gap_id for item in gaps)),
            source_recovery_questions=list(dict.fromkeys(item.question for item in gaps)),
        )

    def _assess(self, candidate: _OpportunityView) -> AINativeCandidateAssessment:
        criteria = [
            self._criterion(
                AINativeCriterion.ECOSYSTEM_SCOPE,
                candidate.scope_level is _SolutionScope.ECOSYSTEM_SERVICE,
                "candidate_is_not_ecosystem_service",
            ),
            self._cross_device(candidate),
            self._ai_removal(candidate),
            self._responsibility_separation(candidate),
            self._criterion(
                AINativeCriterion.REVISION_LOOP,
                bool(candidate.ai_native_case.learning_or_revision_loop),
                "missing_learning_or_revision_loop",
            ),
            self._privacy_and_fallback(candidate),
            self._criterion(
                AINativeCriterion.HUMAN_AUTHORIZATION,
                bool(candidate.ecosystem_blueprint.permission_boundary.strip())
                and bool(candidate.ai_native_case.safety_constraints)
                and bool(candidate.validation_plan.human_review_points),
                "missing_permission_safety_or_human_review_boundary",
            ),
            self._predeployment_validation(candidate),
        ]
        if candidate.gate_status == "blocked":
            existing = criteria[0]
            criteria[0] = AINativeCriterionResult(
                criterion=AINativeCriterion.ECOSYSTEM_SCOPE,
                passed=False,
                issues=list(
                    dict.fromkeys(
                        [
                            *existing.issues,
                            "opportunity_evidence_or_capability_gate_blocked",
                        ]
                    )
                ),
            )
        blocking = list(
            dict.fromkeys(issue for criterion in criteria for issue in criterion.issues)
        )
        status = (
            AINativeCandidateStatus.BLOCKED
            if blocking
            else AINativeCandidateStatus.HUMAN_REVIEW_REQUIRED
        )
        return AINativeCandidateAssessment(
            opportunity_id=candidate.opportunity_id,
            status=status,
            criteria=criteria,
            blocking_issues=blocking,
            human_review_questions=(
                [] if blocking else self._human_questions(candidate.opportunity_id)
            ),
        )

    @staticmethod
    def _criterion(
        criterion: AINativeCriterion, passed: bool, issue: str
    ) -> AINativeCriterionResult:
        return AINativeCriterionResult(
            criterion=criterion,
            passed=passed,
            issues=[] if passed else [issue],
        )

    def _cross_device(self, candidate: _OpportunityView) -> AINativeCriterionResult:
        blueprint = candidate.ecosystem_blueprint
        required_roles = {
            item.role_id for item in blueprint.required_device_roles if not item.optional
        }
        passed = len(required_roles) >= 2 and any(
            flow.from_role_id != flow.to_role_id
            and {flow.from_role_id, flow.to_role_id}.issubset(required_roles)
            for flow in blueprint.cross_device_information_flows
        )
        return self._criterion(
            AINativeCriterion.CROSS_DEVICE_LOOP,
            passed,
            "missing_required_cross_device_closed_loop",
        )

    def _ai_removal(self, candidate: _OpportunityView) -> AINativeCriterionResult:
        removal = candidate.ai_native_case.ai_removal_test
        passed = (
            not removal.core_value_survives_without_ai
            and bool(removal.lost_capabilities_without_ai)
            and bool(removal.rationale.strip())
        )
        return self._criterion(
            AINativeCriterion.AI_REMOVAL,
            passed,
            "core_value_survives_without_ai_or_missing_loss",
        )

    def _responsibility_separation(self, candidate: _OpportunityView) -> AINativeCriterionResult:
        case = candidate.ai_native_case
        model = {item.casefold().strip() for item in case.model_responsibilities}
        deterministic = {item.casefold().strip() for item in case.deterministic_responsibilities}
        passed = bool(model) and bool(deterministic) and not model.intersection(deterministic)
        return self._criterion(
            AINativeCriterion.RESPONSIBILITY_SEPARATION,
            passed,
            "model_and_deterministic_responsibilities_not_separated",
        )

    def _privacy_and_fallback(self, candidate: _OpportunityView) -> AINativeCriterionResult:
        blueprint = candidate.ecosystem_blueprint
        flows_are_bounded = all(
            flow.privacy_constraints and flow.fallback.strip()
            for flow in blueprint.cross_device_information_flows
        )
        passed = (
            all(
                item.strip()
                for item in (
                    blueprint.privacy_boundary,
                    blueprint.offline_behavior,
                    blueprint.fallback_behavior,
                )
            )
            and flows_are_bounded
        )
        return self._criterion(
            AINativeCriterion.PRIVACY_AND_FALLBACK,
            passed,
            "missing_privacy_offline_or_failure_fallback",
        )

    def _predeployment_validation(self, candidate: _OpportunityView) -> AINativeCriterionResult:
        plan = candidate.validation_plan
        scenarios = set(plan.required_scenario_types)
        passed = (
            _ScenarioType.FAILURE in scenarios
            and _ScenarioType.ADVERSARIAL in scenarios
            and bool(plan.success_conditions)
            and bool(plan.failure_conditions)
        )
        return self._criterion(
            AINativeCriterion.PREDEPLOYMENT_VALIDATION,
            passed,
            "validation_plan_missing_failure_or_adversarial_tests",
        )

    @staticmethod
    def _human_questions(opportunity_id: str) -> list[AINativeHumanReviewQuestion]:
        prompts = (
            (
                "open_goal",
                "该机会是否真的需要理解开放式安全目标，而不是一组可以预先穷举的固定规则？",
                "开放目标是否成立属于产品与安全语义判断。",
            ),
            (
                "persistent_state",
                "方案是否跨时间维护家庭安全状态，而不是看到一次事件就发送一次通知？",
                "持续状态不能仅凭字段完整性自动确认。",
            ),
            (
                "active_evidence",
                "证据不足时，方案是否会主动补证、降级或询问用户，而不是强行判断？",
                "主动感知闭环需要人工确认其真实业务含义。",
            ),
            (
                "failure_revision",
                "验证失败后，系统是否能够修订策略，并保留用户授权与可追溯记录？",
                "失败修订是否有效需要人工审查。",
            ),
        )
        return [
            AINativeHumanReviewQuestion(
                question_id=(
                    f"review_{code}_"
                    f"{hashlib.sha256(opportunity_id.encode('utf-8')).hexdigest()[:12]}"
                ),
                opportunity_id=opportunity_id,
                question=question,
                reason=reason,
            )
            for code, question, reason in prompts
        ]

    @staticmethod
    def _revision(task_id: str, assessment: AINativeCandidateAssessment) -> AINativeRevisionRequest:
        canonical = json.dumps(
            {
                "opportunity_id": assessment.opportunity_id,
                "issues": assessment.blocking_issues,
                "task_id": task_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_id = f"revision_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"
        return AINativeRevisionRequest(
            revision_request_id=request_id,
            affected_opportunity_ids=[assessment.opportunity_id],
            affected_task_ids=[task_id],
            reasons=assessment.blocking_issues,
            required_actions=[
                f"修订机会并通过 AI Native 条件：{issue}" for issue in assessment.blocking_issues
            ],
        )
