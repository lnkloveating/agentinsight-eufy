"""Deterministic compiler and policy safety boundary validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.agents.ecosystem_opportunity import EcosystemOpportunityArtifact
from app.agents.security_policy.contracts import (
    CompiledPolicyFallback,
    CompiledPolicyIntervention,
    CompiledPolicyInvariant,
    CompiledPolicyRule,
    CompiledPolicySignal,
    CompiledPolicyStateVariable,
    CompiledSecurityPolicy,
    PolicyCompilationGap,
    PolicyCompilationStatus,
    PolicyFallbackTrigger,
    PolicyIntent,
    PolicyRiskLevel,
    SecurityPolicyArtifact,
    SecurityPolicyCoverage,
    SecurityPolicyModelOutput,
    SecurityPolicyPayload,
    SecurityPolicyVersionDiff,
    policy_gap_id,
    stable_component_id,
    stable_policy_id,
)
from app.agents.technical_feasibility import (
    TechnicalFeasibilityArtifact,
    TechnicalFeasibilityVerdict,
)
from app.schemas.project import AllowedIntervention
from app.workflows.contracts import AgentContext, ResearchTask, ResearchTaskStatus


@dataclass(frozen=True)
class SecurityPolicyValidationError(ValueError):
    message: str
    details: dict[str, object]

    def __str__(self) -> str:
        return self.message


_ADVANCING_VERDICTS = {
    TechnicalFeasibilityVerdict.DEMO_FEASIBLE,
    TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE,
}
_HIGH_IMPACT_ACTIONS = {
    AllowedIntervention.NOTIFY_AUTHORIZED_CONTACT,
    AllowedIntervention.PRESERVE_EVIDENCE,
}
_RISK_ORDER = {
    PolicyRiskLevel.INFORMATIONAL: 0,
    PolicyRiskLevel.LOW: 1,
    PolicyRiskLevel.MEDIUM: 2,
    PolicyRiskLevel.HIGH: 3,
    PolicyRiskLevel.CRITICAL: 4,
    PolicyRiskLevel.UNCERTAIN: 5,
}


class SecurityPolicyCompiler:
    def compile(
        self,
        task: ResearchTask,
        context: AgentContext,
        output: SecurityPolicyModelOutput,
    ) -> SecurityPolicyArtifact:
        opportunity = self._opportunity_artifact(context)
        technical = self._technical_artifact(context)
        previous = self._previous_artifact(context)
        selected_ids = list(dict.fromkeys(context.selected_innovation_ids))
        if not selected_ids:
            raise self._error("Security Policy Compiler requires selected opportunities.")

        technical_by_id = {
            item.opportunity_id: item for item in technical.payload.assessments
        }
        invalid_selection = sorted(
            opportunity_id
            for opportunity_id in selected_ids
            if opportunity_id not in technical_by_id
            or technical_by_id[opportunity_id].verdict not in _ADVANCING_VERDICTS
        )
        if invalid_selection:
            raise self._error(
                "Selected opportunities did not pass Technical Feasibility.",
                invalid_opportunity_ids=invalid_selection,
            )

        model_ids = [item.opportunity_id for item in output.policies]
        if set(model_ids) != set(selected_ids):
            raise self._error(
                "Policy intents must match selected opportunities.",
                selected_opportunity_ids=selected_ids,
                policy_opportunity_ids=model_ids,
            )

        allowed_evidence = self._allowed_evidence(context, opportunity, technical)
        cited = self._cited_evidence(output)
        unsupported_evidence = sorted(cited - allowed_evidence)
        if unsupported_evidence:
            raise self._error(
                "Security policy cites Evidence outside the bounded context.",
                unsupported_evidence_ids=unsupported_evidence,
            )

        opportunities = {
            item.opportunity_id: item for item in opportunity.payload.opportunities
        }
        missing_opportunities = sorted(set(selected_ids) - set(opportunities))
        if missing_opportunities:
            raise self._error(
                "Selected opportunities are absent from the source portfolio.",
                missing_opportunity_ids=missing_opportunities,
            )

        compiled = [
            self._compile_policy(
                intent,
                context,
                opportunities[intent.opportunity_id],
                technical_by_id[intent.opportunity_id],
                previous,
            )
            for intent in output.policies
        ]
        compiled.sort(key=lambda item: item.policy_id)
        gaps = [
            PolicyCompilationGap(
                gap_id=policy_gap_id(item.question, item.affected_opportunity_ids),
                **item.model_dump(mode="python"),
            )
            for item in output.compilation_gaps
        ]
        diff = self._diff(previous, compiled)
        conditional_count = sum(
            item.compilation_status is PolicyCompilationStatus.CONDITIONAL
            for item in compiled
        )
        coverage = SecurityPolicyCoverage(
            selected_opportunity_count=len(selected_ids),
            compiled_policy_count=len(compiled),
            conditional_policy_count=conditional_count,
            authorized_signal_type_count=len(context.brief.authorized_signal_types),
            allowed_intervention_count=len(
                context.brief.intervention_boundary.allowed_interventions
            ),
            evidence_context_hash=(
                context.evidence_context.context_hash
                if context.evidence_context is not None
                else "0" * 64
            ),
        )
        payload = SecurityPolicyPayload(
            source_technical_artifact_id=technical.artifact_id,
            source_opportunity_artifact_id=opportunity.artifact_id,
            selected_opportunity_ids=selected_ids,
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            policies=compiled,
            compilation_gaps=gaps,
            version_diff=diff,
            coverage=coverage,
        )
        partial = bool(conditional_count or gaps or output.unknowns)
        return SecurityPolicyArtifact(
            artifact_id=f"artifact_{task.task_id}_{context.iteration + 1}",
            task_id=task.task_id,
            status=(ResearchTaskStatus.PARTIAL if partial else ResearchTaskStatus.COMPLETED),
            payload=payload,
            evidence_ids=sorted(cited),
            contradictions=[],
            unknowns=list(
                dict.fromkeys([*output.unknowns, *(item.question for item in gaps)])
            ),
            quality_score=self._quality_score(compiled, gaps),
            errors=[],
        )

    def _compile_policy(
        self,
        intent: PolicyIntent,
        context: AgentContext,
        opportunity: Any,
        technical: Any,
        previous: SecurityPolicyArtifact | None,
    ) -> CompiledSecurityPolicy:
        policy_id = stable_policy_id(intent.opportunity_id)
        allowed_signals = set(context.brief.authorized_signal_types)
        unsupported_signals = sorted(
            item.signal_type.value
            for item in intent.signal_requests
            if item.signal_type not in allowed_signals
        )
        if unsupported_signals:
            raise self._error(
                "Policy requests signals outside the Research Brief authorization.",
                opportunity_id=intent.opportunity_id,
                unauthorized_signal_types=unsupported_signals,
            )

        role_ids = {
            role.role_id for role in opportunity.ecosystem_blueprint.required_device_roles
        }
        unknown_roles = sorted(
            {item.source_role_id for item in intent.signal_requests} - role_ids
        )
        if unknown_roles:
            raise self._error(
                "Policy references device roles absent from the ecosystem blueprint.",
                opportunity_id=intent.opportunity_id,
                unknown_role_ids=unknown_roles,
            )

        allowed_actions = set(
            context.brief.intervention_boundary.allowed_interventions
        )
        invalid_actions = sorted(
            item.action.value
            for item in intent.intervention_ladder
            if item.action not in allowed_actions
        )
        if invalid_actions:
            raise self._error(
                "Policy contains interventions outside the Research Brief boundary.",
                opportunity_id=intent.opportunity_id,
                unauthorized_interventions=invalid_actions,
            )
        unsafe_actions = sorted(
            item.action.value
            for item in intent.intervention_ladder
            if item.action in _HIGH_IMPACT_ACTIONS
            and not item.human_approval_required
        )
        if unsafe_actions:
            raise self._error(
                "High-impact policy actions require human approval.",
                opportunity_id=intent.opportunity_id,
                unsafe_interventions=unsafe_actions,
            )

        references = {
            *(f"state:{item.key}" for item in intent.state_variables),
            *(f"signal:{item.key}" for item in intent.signal_requests),
        }
        invalid_references = sorted(
            {
                condition.reference
                for rule in intent.risk_rules
                for condition in rule.conditions
                if condition.reference not in references
            }
        )
        if invalid_references:
            raise self._error(
                "Policy conditions reference undefined state or signals.",
                opportunity_id=intent.opportunity_id,
                invalid_references=invalid_references,
            )

        states = [
            CompiledPolicyStateVariable(
                state_id=stable_component_id(
                    "state", policy_id, item.model_dump(mode="json")
                ),
                **item.model_dump(mode="python"),
            )
            for item in intent.state_variables
        ]
        signals = [
            CompiledPolicySignal(
                signal_id=stable_component_id(
                    "signal", policy_id, item.model_dump(mode="json")
                ),
                **item.model_dump(mode="python"),
            )
            for item in intent.signal_requests
        ]
        rules = [
            CompiledPolicyRule(
                rule_id=stable_component_id(
                    "rule", policy_id, item.model_dump(mode="json")
                ),
                **item.model_dump(mode="python"),
            )
            for item in intent.risk_rules
        ]
        interventions = [
            CompiledPolicyIntervention(
                intervention_id=stable_component_id(
                    "action", policy_id, item.model_dump(mode="json")
                ),
                **item.model_dump(mode="python"),
            )
            for item in sorted(
                intent.intervention_ladder,
                key=lambda item: (_RISK_ORDER[item.minimum_risk_level], item.action.value),
            )
        ]
        previous_version = self._previous_policy_version(previous, policy_id)
        status = (
            PolicyCompilationStatus.CONDITIONAL
            if technical.verdict
            is TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE
            else PolicyCompilationStatus.COMPILED
        )
        prerequisites = list(
            dict.fromkeys(
                [
                    *technical.gate_issues,
                    *(
                        requirement.condition
                        for requirement in technical.requirements
                        if requirement.condition is not None
                    ),
                ]
            )
        )
        draft = CompiledSecurityPolicy(
            policy_id=policy_id,
            policy_version=previous_version + 1,
            opportunity_id=intent.opportunity_id,
            policy_name=intent.policy_name,
            objective=intent.objective,
            compilation_status=status,
            state_variables=states,
            signal_requests=signals,
            risk_rules=rules,
            intervention_ladder=interventions,
            fallbacks=self._fallbacks(policy_id, allowed_actions),
            invariants=self._invariants(policy_id, context),
            technical_prerequisites=prerequisites,
            assumptions=intent.assumptions,
            evidence_ids=sorted(
                {
                    *intent.evidence_ids,
                    *(
                        evidence_id
                        for rule in intent.risk_rules
                        for evidence_id in rule.evidence_ids
                    ),
                }
            ),
            dsl_hash="0" * 64,
        )
        # Versions are metadata. Identical policy semantics must keep the same hash.
        canonical = draft.model_dump(
            mode="json", exclude={"dsl_hash", "policy_version"}
        )
        dsl_hash = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return draft.model_copy(update={"dsl_hash": dsl_hash})

    @staticmethod
    def _fallbacks(
        policy_id: str,
        allowed_actions: set[AllowedIntervention],
    ) -> list[CompiledPolicyFallback]:
        def choose(*actions: AllowedIntervention) -> AllowedIntervention:
            for action in actions:
                if action in allowed_actions:
                    return action
            raise SecurityPolicyValidationError(
                "Research Brief has no safe fallback intervention.",
                {"allowed_interventions": sorted(item.value for item in allowed_actions)},
            )

        definitions = {
            PolicyFallbackTrigger.SIGNAL_UNAVAILABLE: (
                choose(
                    AllowedIntervention.REQUEST_ADDITIONAL_SIGNAL,
                    AllowedIntervention.ASK_USER,
                    AllowedIntervention.CONTINUE_OBSERVING,
                ),
                "mark_state_uncertain",
                "Required signal is unavailable; never infer a positive safety state.",
            ),
            PolicyFallbackTrigger.DEVICE_OFFLINE: (
                choose(
                    AllowedIntervention.ASK_USER,
                    AllowedIntervention.LOCAL_PROMPT,
                    AllowedIntervention.CONTINUE_OBSERVING,
                ),
                "mark_device_coverage_degraded",
                "Device loss reduces coverage and must remain visible.",
            ),
            PolicyFallbackTrigger.NETWORK_OFFLINE: (
                choose(
                    AllowedIntervention.LOCAL_PROMPT,
                    AllowedIntervention.CONTINUE_OBSERVING,
                ),
                "use_local_low_risk_mode",
                "Network loss cannot authorize a higher-impact action.",
            ),
            PolicyFallbackTrigger.UNCERTAIN_STATE: (
                choose(
                    AllowedIntervention.ASK_USER,
                    AllowedIntervention.REQUEST_ADDITIONAL_SIGNAL,
                    AllowedIntervention.CONTINUE_OBSERVING,
                ),
                "retain_uncertain_risk",
                "Uncertainty is explicit and cannot be rewritten as safety or danger.",
            ),
            PolicyFallbackTrigger.PERMISSION_DENIED: (
                choose(AllowedIntervention.CONTINUE_OBSERVING),
                "suppress_unauthorized_action",
                "Denied permission always blocks the requested action.",
            ),
        }
        return [
            CompiledPolicyFallback(
                fallback_id=stable_component_id(
                    "fallback", policy_id, {"trigger": trigger.value}
                ),
                trigger=trigger,
                action=action,
                human_approval_required=action in _HIGH_IMPACT_ACTIONS,
                safe_state=safe_state,
                rationale=rationale,
            )
            for trigger, (action, safe_state, rationale) in definitions.items()
        ]

    @staticmethod
    def _invariants(policy_id: str, context: AgentContext) -> list[CompiledPolicyInvariant]:
        statements = [
            ("dry_run_only", "Policy evaluation cannot control a real household device."),
            (
                "authorized_signals_only",
                "Signals are limited to: "
                + ", ".join(item.value for item in context.brief.authorized_signal_types),
            ),
            (
                "allowed_interventions_only",
                "Interventions are limited to: "
                + ", ".join(
                    item.value
                    for item in context.brief.intervention_boundary.allowed_interventions
                ),
            ),
            (
                "human_approval",
                "Every high-impact action requires explicit human approval.",
            ),
            (
                "privacy_boundary",
                "Raw media allowed: "
                f"{context.brief.privacy_boundary.raw_media_allowed}; retention: "
                f"{context.brief.privacy_boundary.retention_policy}",
            ),
            *(
                ("prohibited_action", f"Prohibited action: {item}")
                for item in context.brief.intervention_boundary.prohibited_actions
            ),
            *(
                ("forbidden_inference", f"Forbidden inference: {item}")
                for item in context.brief.forbidden_inferences
            ),
        ]
        return [
            CompiledPolicyInvariant(
                invariant_id=stable_component_id(
                    "invariant", policy_id, {"kind": kind, "statement": statement}
                ),
                kind=kind,
                statement=statement,
            )
            for kind, statement in statements
        ]

    @staticmethod
    def _diff(
        previous: SecurityPolicyArtifact | None,
        current: list[CompiledSecurityPolicy],
    ) -> SecurityPolicyVersionDiff:
        previous_by_id = (
            {item.policy_id: item for item in previous.payload.policies}
            if previous is not None
            else {}
        )
        current_by_id = {item.policy_id: item for item in current}
        shared = set(previous_by_id) & set(current_by_id)
        return SecurityPolicyVersionDiff(
            previous_artifact_id=previous.artifact_id if previous is not None else None,
            added_policy_ids=sorted(set(current_by_id) - set(previous_by_id)),
            removed_policy_ids=sorted(set(previous_by_id) - set(current_by_id)),
            changed_policy_ids=sorted(
                policy_id
                for policy_id in shared
                if previous_by_id[policy_id].dsl_hash != current_by_id[policy_id].dsl_hash
            ),
            unchanged_policy_ids=sorted(
                policy_id
                for policy_id in shared
                if previous_by_id[policy_id].dsl_hash == current_by_id[policy_id].dsl_hash
            ),
        )

    @staticmethod
    def _previous_policy_version(
        previous: SecurityPolicyArtifact | None, policy_id: str
    ) -> int:
        if previous is None:
            return 0
        item = next(
            (item for item in previous.payload.policies if item.policy_id == policy_id),
            None,
        )
        return item.policy_version if item is not None else 0

    @staticmethod
    def _opportunity_artifact(context: AgentContext) -> EcosystemOpportunityArtifact:
        raw = context.upstream_artifacts.get("ecosystem_opportunity")
        if raw is None:
            raise SecurityPolicyValidationError(
                "Security Policy Compiler requires Ecosystem Opportunity.", {}
            )
        return EcosystemOpportunityArtifact.from_research_artifact(raw)

    @staticmethod
    def _technical_artifact(context: AgentContext) -> TechnicalFeasibilityArtifact:
        raw = context.upstream_artifacts.get("technical_feasibility")
        if raw is None:
            raise SecurityPolicyValidationError(
                "Security Policy Compiler requires Technical Feasibility.", {}
            )
        return TechnicalFeasibilityArtifact.from_research_artifact(raw)

    @staticmethod
    def _previous_artifact(context: AgentContext) -> SecurityPolicyArtifact | None:
        raw = context.upstream_artifacts.get("security_policy")
        return SecurityPolicyArtifact.from_research_artifact(raw) if raw is not None else None

    @staticmethod
    def _allowed_evidence(
        context: AgentContext,
        opportunity: EcosystemOpportunityArtifact,
        technical: TechnicalFeasibilityArtifact,
    ) -> set[str]:
        return {
            *opportunity.evidence_ids,
            *technical.evidence_ids,
            *(
                item.evidence_id
                for item in (
                    context.evidence_context.items
                    if context.evidence_context is not None
                    else []
                )
            ),
        }

    @staticmethod
    def _cited_evidence(output: SecurityPolicyModelOutput) -> set[str]:
        return {
            *output.summary_evidence_ids,
            *(evidence_id for policy in output.policies for evidence_id in policy.evidence_ids),
            *(
                evidence_id
                for policy in output.policies
                for rule in policy.risk_rules
                for evidence_id in rule.evidence_ids
            ),
        }

    @staticmethod
    def _quality_score(
        policies: list[CompiledSecurityPolicy], gaps: list[PolicyCompilationGap]
    ) -> float:
        conditional = sum(
            item.compilation_status is PolicyCompilationStatus.CONDITIONAL
            for item in policies
        )
        return max(0.0, round(100 - conditional * 8 - len(gaps) * 5, 2))

    @staticmethod
    def _error(message: str, **details: object) -> SecurityPolicyValidationError:
        return SecurityPolicyValidationError(message, details)
