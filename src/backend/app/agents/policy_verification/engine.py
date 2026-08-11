"""Deterministic scenario generation and execution for compiled policy DSL."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import groupby

from app.agents.policy_verification.contracts import (
    PolicyVerificationArtifact,
    PolicyVerificationCoverage,
    PolicyVerificationGap,
    PolicyVerificationPayload,
    PolicyVerificationRunCreate,
    PolicyVerificationScenario,
    PolicyVerificationScenarioCreate,
    PolicyVerificationScenarioResult,
    Scalar,
    ScenarioAssertion,
    ScenarioOrigin,
    ScenarioTraceStep,
    ScenarioValueUpdate,
    VerificationScenarioCategory,
    VerificationStatus,
    verification_gap_id,
    verification_scenario_id,
)
from app.agents.security_policy import (
    CompiledSecurityPolicy,
    PolicyConditionIntent,
    PolicyConditionOperator,
    PolicyFallbackTrigger,
    PolicyRiskLevel,
    SecurityPolicyArtifact,
)
from app.schemas.project import AllowedIntervention
from app.workflows.contracts import ResearchTask, ResearchTaskStatus

_RISK_ORDER = {
    PolicyRiskLevel.INFORMATIONAL: 0,
    PolicyRiskLevel.LOW: 1,
    PolicyRiskLevel.MEDIUM: 2,
    PolicyRiskLevel.HIGH: 3,
    PolicyRiskLevel.CRITICAL: 4,
    PolicyRiskLevel.UNCERTAIN: 5,
}
_CATEGORY_BY_FALLBACK = {
    PolicyFallbackTrigger.SIGNAL_UNAVAILABLE: VerificationScenarioCategory.SIGNAL_UNAVAILABLE,
    PolicyFallbackTrigger.DEVICE_OFFLINE: VerificationScenarioCategory.DEVICE_OFFLINE,
    PolicyFallbackTrigger.NETWORK_OFFLINE: VerificationScenarioCategory.NETWORK_OFFLINE,
    PolicyFallbackTrigger.UNCERTAIN_STATE: VerificationScenarioCategory.UNCERTAIN_STATE,
    PolicyFallbackTrigger.PERMISSION_DENIED: VerificationScenarioCategory.PERMISSION_DENIED,
}


@dataclass(frozen=True)
class PolicyVerificationError(ValueError):
    message: str
    details: dict[str, object]

    def __str__(self) -> str:
        return self.message


class SecurityPolicyVerificationEngine:
    """Runs policy JSON as data; it never imports a device-control integration."""

    def verify(
        self,
        task: ResearchTask,
        policy_artifact: SecurityPolicyArtifact,
        request: PolicyVerificationRunCreate,
        *,
        iteration: int = 0,
    ) -> PolicyVerificationArtifact:
        policies = {item.policy_id: item for item in policy_artifact.payload.policies}
        generated, gaps = self._generate_scenarios(policies.values())
        user = [self._user_scenario(item, policies) for item in request.scenarios]
        scenarios = [*generated, *user]
        results = [self._run_scenario(item, policies[item.policy_id]) for item in scenarios]
        failed = sum(item.status is VerificationStatus.FAILED for item in results)
        inconclusive = sum(
            item.status is VerificationStatus.INCONCLUSIVE for item in results
        )
        passed = len(results) - failed - inconclusive
        if failed:
            status = VerificationStatus.FAILED
            recommendation = "策略存在失败断言，必须修订后重新验证。"
        elif inconclusive and passed == 0:
            status = VerificationStatus.INCONCLUSIVE
            recommendation = "当前场景无法形成可验证结论，需要补充资料。"
        elif gaps or inconclusive:
            status = VerificationStatus.CONDITIONALLY_PASSED
            recommendation = "结构化验证通过，但仍有未覆盖条件，需要补证或限制试点范围。"
        else:
            status = VerificationStatus.PASSED
            recommendation = "策略通过当前 dry-run 场景，可进入商业评估；不代表真实设备已部署。"
        evidence_ids = sorted(
            {
                *policy_artifact.evidence_ids,
                *(evidence_id for item in scenarios for evidence_id in item.evidence_ids),
            }
        )
        fallback_covered = len(
            {
                item.fallback_trigger
                for item in scenarios
                if item.fallback_trigger is not None
            }
        )
        payload = PolicyVerificationPayload(
            source_policy_artifact_id=policy_artifact.artifact_id,
            source_policy_versions={
                item.policy_id: item.policy_version for item in policies.values()
            },
            verification_status=status,
            recommendation=recommendation,
            scenarios=scenarios,
            results=results,
            validation_gaps=gaps,
            coverage=PolicyVerificationCoverage(
                policy_count=len(policies),
                scenario_count=len(scenarios),
                passed_count=passed,
                failed_count=failed,
                inconclusive_count=inconclusive,
                generated_count=len(generated),
                user_defined_count=len(user),
                fallback_types_covered=fallback_covered,
            ),
        )
        unknowns = [item.question for item in gaps]
        return PolicyVerificationArtifact(
            artifact_id=f"artifact_{task.task_id}_{iteration + 1}",
            task_id=task.task_id,
            status=(
                ResearchTaskStatus.PARTIAL
                if status
                in {
                    VerificationStatus.CONDITIONALLY_PASSED,
                    VerificationStatus.INCONCLUSIVE,
                }
                else ResearchTaskStatus.COMPLETED
            ),
            payload=payload,
            evidence_ids=evidence_ids,
            unknowns=unknowns,
            quality_score=self._quality_score(results, gaps),
        )

    def _generate_scenarios(
        self, policies: Iterable[CompiledSecurityPolicy]
    ) -> tuple[list[PolicyVerificationScenario], list[PolicyVerificationGap]]:
        scenarios: list[PolicyVerificationScenario] = []
        gaps: list[PolicyVerificationGap] = []
        for policy in policies:
            for rule in policy.risk_rules:
                updates = self._satisfying_updates(rule.conditions)
                if updates is None:
                    question = (
                        f"如何验证策略 {policy.policy_id} 的规则 "
                        f"{rule.rule_id} 的状态变化条件？"
                    )
                    gaps.append(
                        PolicyVerificationGap(
                            gap_id=verification_gap_id(question, [policy.policy_id]),
                            question=question,
                            reason="changed/unchanged 或冲突条件不能从单点 dry-run 输入可靠合成。",
                            affected_policy_ids=[policy.policy_id],
                            recommended_source_types=[
                                "authorized_event_sequence",
                                "simulation_fixture",
                            ],
                        )
                    )
                    continue
                expected_action = self._action_for_risk(
                    policy, rule.resulting_risk_level
                )
                raw = PolicyVerificationScenarioCreate(
                    name=f"验证风险规则：{rule.description}",
                    policy_id=policy.policy_id,
                    category=VerificationScenarioCategory.RISK_RULE,
                    updates=updates,
                    expected_risk_level=rule.resulting_risk_level,
                    expected_action=expected_action,
                    rationale="由已编译规则确定性生成，验证规则组合和干预阶梯。",
                    evidence_ids=rule.evidence_ids,
                )
                scenarios.append(self._generated_scenario(raw))
            for fallback in policy.fallbacks:
                raw = PolicyVerificationScenarioCreate(
                    name=f"验证失败降级：{fallback.trigger.value}",
                    policy_id=policy.policy_id,
                    category=_CATEGORY_BY_FALLBACK[fallback.trigger],
                    fallback_trigger=fallback.trigger,
                    expected_risk_level=PolicyRiskLevel.UNCERTAIN,
                    expected_action=fallback.action,
                    rationale=fallback.rationale,
                    evidence_ids=policy.evidence_ids,
                )
                scenarios.append(self._generated_scenario(raw))
        if not scenarios:
            raise PolicyVerificationError(
                "Security Policy contains no verifiable rules or fallbacks.", {}
            )
        return scenarios, gaps

    def _user_scenario(
        self,
        raw: PolicyVerificationScenarioCreate,
        policies: dict[str, CompiledSecurityPolicy],
    ) -> PolicyVerificationScenario:
        policy = policies.get(raw.policy_id)
        if policy is None:
            raise PolicyVerificationError(
                "User scenario references an unknown policy.",
                {"policy_id": raw.policy_id},
            )
        valid_refs = {
            *(f"state:{item.key}" for item in policy.state_variables),
            *(f"signal:{item.key}" for item in policy.signal_requests),
        }
        invalid = sorted({item.reference for item in raw.updates} - valid_refs)
        if invalid:
            raise PolicyVerificationError(
                "User scenario references state or signals outside the policy.",
                {"invalid_references": invalid},
            )
        unsupported_evidence = sorted(set(raw.evidence_ids) - set(policy.evidence_ids))
        if unsupported_evidence:
            raise PolicyVerificationError(
                "User scenario cites Evidence outside the source policy.",
                {"unsupported_evidence_ids": unsupported_evidence},
            )
        value = raw.model_dump(mode="json")
        return PolicyVerificationScenario(
            scenario_id=verification_scenario_id(raw.policy_id, "user", value),
            origin=ScenarioOrigin.USER,
            **raw.model_dump(mode="python"),
        )

    @staticmethod
    def _generated_scenario(
        raw: PolicyVerificationScenarioCreate,
    ) -> PolicyVerificationScenario:
        value = raw.model_dump(mode="json")
        return PolicyVerificationScenario(
            scenario_id=verification_scenario_id(raw.policy_id, raw.category.value, value),
            origin=ScenarioOrigin.GENERATED,
            **raw.model_dump(mode="python"),
        )

    def _run_scenario(
        self,
        scenario: PolicyVerificationScenario,
        policy: CompiledSecurityPolicy,
    ) -> PolicyVerificationScenarioResult:
        values: dict[str, Scalar] = {
            f"state:{item.key}": item.initial_value for item in policy.state_variables
        }
        fallback = None
        action: AllowedIntervention | None
        trace: list[ScenarioTraceStep] = []
        if scenario.fallback_trigger is not None:
            fallback = next(
                item
                for item in policy.fallbacks
                if item.trigger is scenario.fallback_trigger
            )
            risk = PolicyRiskLevel.UNCERTAIN
            action = fallback.action
            fired: list[str] = []
            trace.append(
                ScenarioTraceStep(
                    sequence=0,
                    event=f"fallback:{scenario.fallback_trigger.value}",
                    risk_level=risk,
                    action=action,
                    fallback_id=fallback.fallback_id,
                )
            )
        else:
            fired = []
            risk = PolicyRiskLevel.INFORMATIONAL
            action = None
            ordered = sorted(
                scenario.updates, key=lambda item: (item.at_seconds, item.reference)
            )
            for sequence, (at_seconds, group) in enumerate(
                groupby(ordered, key=lambda item: item.at_seconds)
            ):
                updates = list(group)
                changed = {
                    item.reference
                    for item in updates
                    if values.get(item.reference) != item.value
                }
                values.update({item.reference: item.value for item in updates})
                matched = [
                    rule
                    for rule in policy.risk_rules
                    if self._rule_matches(
                        rule.conditions,
                        rule.require_all_conditions,
                        values,
                        changed,
                    )
                ]
                fired = [item.rule_id for item in matched]
                risk = max(
                    (item.resulting_risk_level for item in matched),
                    key=lambda item: _RISK_ORDER[item],
                    default=PolicyRiskLevel.INFORMATIONAL,
                )
                action = self._action_for_risk(policy, risk)
                trace.append(
                    ScenarioTraceStep(
                        sequence=sequence,
                        event=f"t+{at_seconds}s apply {len(updates)} updates",
                        risk_level=risk,
                        action=action,
                        fired_rule_ids=fired,
                    )
                )
        assertions: list[ScenarioAssertion] = []
        if scenario.expected_risk_level is not None:
            assertions.append(
                ScenarioAssertion(
                    assertion="risk_level_matches",
                    passed=risk is scenario.expected_risk_level,
                    expected=scenario.expected_risk_level.value,
                    observed=risk.value,
                )
            )
        if scenario.expected_action is not None:
            assertions.append(
                ScenarioAssertion(
                    assertion="intervention_matches",
                    passed=action is scenario.expected_action,
                    expected=scenario.expected_action.value,
                    observed=action.value if action is not None else "none",
                )
            )
        status = (
            VerificationStatus.PASSED
            if all(item.passed for item in assertions)
            else VerificationStatus.FAILED
        )
        return PolicyVerificationScenarioResult(
            scenario_id=scenario.scenario_id,
            policy_id=policy.policy_id,
            category=scenario.category,
            status=status,
            observed_risk_level=risk,
            observed_action=action,
            fired_rule_ids=fired,
            fallback_id=fallback.fallback_id if fallback is not None else None,
            assertions=assertions,
            trace=trace,
            evidence_ids=scenario.evidence_ids,
        )

    @staticmethod
    def _satisfying_updates(
        conditions: list[PolicyConditionIntent],
    ) -> list[ScenarioValueUpdate] | None:
        values: dict[str, Scalar] = {}
        temporal_references = {
            item.reference
            for item in conditions
            if item.operator
            in {PolicyConditionOperator.CHANGED, PolicyConditionOperator.UNCHANGED}
        }
        if any(
            item.reference in temporal_references
            and item.operator
            not in {PolicyConditionOperator.CHANGED, PolicyConditionOperator.UNCHANGED}
            for item in conditions
        ):
            return None
        temporal_updates: list[ScenarioValueUpdate] = []
        for condition in conditions:
            operator = condition.operator
            if operator is PolicyConditionOperator.NOT_EXISTS:
                return None
            if operator is PolicyConditionOperator.CHANGED:
                temporal_updates.append(
                    ScenarioValueUpdate(
                        at_seconds=1, reference=condition.reference, value=True
                    )
                )
                continue
            if operator is PolicyConditionOperator.UNCHANGED:
                temporal_updates.extend(
                    [
                        ScenarioValueUpdate(
                            at_seconds=0, reference=condition.reference, value=True
                        ),
                        ScenarioValueUpdate(
                            at_seconds=1, reference=condition.reference, value=True
                        ),
                    ]
                )
                continue
            value = condition.value
            if operator is PolicyConditionOperator.EXISTS:
                value = True
            elif operator is PolicyConditionOperator.NE:
                value = "__different__" if not isinstance(value, bool) else not value
            elif operator is PolicyConditionOperator.GT:
                value = float(value) + 1 if isinstance(value, (int, float)) else None
            elif operator is PolicyConditionOperator.GTE:
                value = value
            elif operator is PolicyConditionOperator.LT:
                value = float(value) - 1 if isinstance(value, (int, float)) else None
            elif operator is PolicyConditionOperator.LTE:
                value = value
            if value is None or (
                condition.reference in values and values[condition.reference] != value
            ):
                return None
            values[condition.reference] = value
        return [
            ScenarioValueUpdate(at_seconds=1, reference=reference, value=value)
            for reference, value in sorted(values.items())
        ] + temporal_updates

    @classmethod
    def _rule_matches(
        cls,
        conditions: list[PolicyConditionIntent],
        require_all: bool,
        values: dict[str, Scalar],
        changed_references: set[str],
    ) -> bool:
        outcomes = [
            cls._condition_matches(item, values, changed_references)
            for item in conditions
        ]
        return all(outcomes) if require_all else any(outcomes)

    @staticmethod
    def _condition_matches(
        condition: PolicyConditionIntent,
        values: dict[str, Scalar],
        changed_references: set[str],
    ) -> bool:
        exists = condition.reference in values and values[condition.reference] is not None
        actual = values.get(condition.reference)
        expected = condition.value
        operator = condition.operator
        if operator is PolicyConditionOperator.CHANGED:
            return condition.reference in changed_references
        if operator is PolicyConditionOperator.UNCHANGED:
            return exists and condition.reference not in changed_references
        if operator is PolicyConditionOperator.EXISTS:
            return exists
        if operator is PolicyConditionOperator.NOT_EXISTS:
            return not exists
        if operator is PolicyConditionOperator.EQ:
            return actual == expected
        if operator is PolicyConditionOperator.NE:
            return actual != expected
        if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
            return False
        if operator is PolicyConditionOperator.GT:
            return actual > expected
        if operator is PolicyConditionOperator.GTE:
            return actual >= expected
        if operator is PolicyConditionOperator.LT:
            return actual < expected
        if operator is PolicyConditionOperator.LTE:
            return actual <= expected
        return False

    @staticmethod
    def _action_for_risk(
        policy: CompiledSecurityPolicy, risk: PolicyRiskLevel
    ) -> AllowedIntervention | None:
        eligible = [
            item
            for item in policy.intervention_ladder
            if _RISK_ORDER[item.minimum_risk_level] <= _RISK_ORDER[risk]
        ]
        return eligible[-1].action if eligible else None

    @staticmethod
    def _quality_score(
        results: list[PolicyVerificationScenarioResult],
        gaps: list[PolicyVerificationGap],
    ) -> float:
        failures = sum(item.status is VerificationStatus.FAILED for item in results)
        return max(0.0, round(100 - failures * 10 - len(gaps) * 5, 2))
