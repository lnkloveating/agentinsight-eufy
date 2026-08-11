"""Deterministic evidence and upstream-bound Commercial Evaluation v2 validation."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.commercial_evaluation_v2.contracts import (
    CommercialClaim,
    CommercialConclusionStatus,
    CommercialDimensionConclusion,
    CommercialDimensionIntent,
    CommercialEvaluationArtifact,
    CommercialEvaluationCoverage,
    CommercialEvaluationModelOutput,
    CommercialEvaluationPayload,
    CommercialGap,
    CommercialRecommendation,
    DeliveryOperationsConclusion,
    commercial_claim_id,
    commercial_gap_id,
)
from app.agents.ecosystem_opportunity import EcosystemOpportunityArtifact
from app.agents.policy_verification import (
    PolicyVerificationArtifact,
    VerificationStatus,
)
from app.agents.technical_feasibility import (
    TechnicalFeasibilityArtifact,
    TechnicalFeasibilityVerdict,
)
from app.agents.user_research import UserResearchArtifact
from app.schemas.evidence import EvidenceClaimType
from app.workflows.contracts import (
    AgentContext,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)

_BUSINESS_EVIDENCE_TYPES = {
    EvidenceClaimType.FACT.value,
    EvidenceClaimType.MARKET_FACT.value,
    EvidenceClaimType.PRICE_OBSERVATION.value,
    EvidenceClaimType.CHANNEL_AVAILABILITY.value,
    EvidenceClaimType.SELLER_INFORMATION.value,
    EvidenceClaimType.PROMOTION.value,
}
_STATUS_ORDER = {
    CommercialConclusionStatus.SUPPORTED: 0,
    CommercialConclusionStatus.CONDITIONAL: 1,
    CommercialConclusionStatus.INSUFFICIENT_EVIDENCE: 2,
    CommercialConclusionStatus.UNSUPPORTED: 3,
}


@dataclass(frozen=True)
class CommercialEvaluationValidationError(ValueError):
    message: str
    details: dict[str, object]

    def __str__(self) -> str:
        return self.message


class CommercialEvaluationOutputValidator:
    def validate(
        self,
        task: ResearchTask,
        context: AgentContext,
        output: CommercialEvaluationModelOutput,
    ) -> CommercialEvaluationArtifact:
        user = self._user_artifact(context)
        opportunity = self._opportunity_artifact(context)
        technical = self._technical_artifact(context)
        verification = self._verification_artifact(context)
        selected = list(
            dict.fromkeys(
                context.selected_innovation_ids
                or technical.payload.selected_opportunity_ids
            )
        )
        known_opportunities = {
            item.opportunity_id for item in opportunity.payload.opportunities
        }
        unknown_opportunities = sorted(set(selected) - known_opportunities)
        if not selected or unknown_opportunities:
            raise self._error(
                "Commercial Evaluation requires valid selected ecosystem opportunities.",
                unknown_opportunity_ids=unknown_opportunities,
            )
        technical_scope = set(technical.payload.selected_opportunity_ids)
        outside_technical_scope = sorted(set(selected) - technical_scope)
        if outside_technical_scope:
            raise self._error(
                "Commercial Evaluation can only consume technically evaluated opportunities.",
                outside_technical_scope=outside_technical_scope,
            )
        if verification.payload.verification_status in {
            VerificationStatus.FAILED,
            VerificationStatus.INCONCLUSIVE,
        }:
            raise self._error(
                "Commercial Evaluation cannot advance a failed or inconclusive policy.",
                verification_status=verification.payload.verification_status.value,
            )
        allowed_evidence = self._allowed_evidence(
            context, user, opportunity, technical, verification
        )
        cited = self._cited_evidence(output)
        unsupported = sorted(cited - allowed_evidence)
        if unsupported:
            raise self._error(
                "Commercial Evaluation cites Evidence outside the bounded context.",
                unsupported_evidence_ids=unsupported,
            )
        user_evidence = set(user.evidence_ids)
        invalid_user = sorted(
            {
                evidence_id
                for claim in output.user_value.claims
                for evidence_id in claim.evidence_ids
            }
            - user_evidence
        )
        if invalid_user:
            raise self._error(
                "User value claims must cite User Research Evidence.",
                invalid_user_value_evidence_ids=invalid_user,
            )
        claim_type_by_id = {
            item.evidence_id: item.claim_type
            for item in (
                context.evidence_context.items
                if context.evidence_context is not None
                else []
            )
        }
        invalid_business = sorted(
            {
                evidence_id
                for claim in output.business_model.claims
                for evidence_id in claim.evidence_ids
                if claim_type_by_id.get(evidence_id) not in _BUSINESS_EVIDENCE_TYPES
            }
        )
        if invalid_business:
            raise self._error(
                "Business claims require market, price, channel or enterprise facts.",
                invalid_business_evidence_ids=invalid_business,
            )
        user_value = self._dimension("user_value", output.user_value)
        business_model = self._dimension("business_model", output.business_model)
        delivery = self._delivery(technical, verification, selected)
        gaps = [
            CommercialGap(
                gap_id=commercial_gap_id(
                    item.question, item.affected_opportunity_ids
                ),
                **item.model_dump(mode="python"),
            )
            for item in output.commercial_gaps
        ]
        invalid_gap_ids = sorted(
            {
                opportunity_id
                for item in gaps
                for opportunity_id in item.affected_opportunity_ids
            }
            - set(selected)
        )
        if invalid_gap_ids:
            raise self._error(
                "Commercial gaps reference opportunities outside the selected scope.",
                invalid_opportunity_ids=invalid_gap_ids,
            )
        insufficient_dimensions = [
            name
            for name, dimension in (
                ("user_value", user_value),
                ("business_model", business_model),
            )
            if dimension.status is CommercialConclusionStatus.INSUFFICIENT_EVIDENCE
        ]
        if insufficient_dimensions and not gaps:
            raise self._error(
                "Insufficient commercial conclusions require explicit recovery gaps.",
                insufficient_dimensions=insufficient_dimensions,
            )
        recommendation = self._recommendation(
            user_value.status,
            business_model.status,
            delivery.status,
            bool(gaps),
        )
        reason = self._recommendation_reason(
            recommendation, user_value.status, business_model.status, delivery.status
        )
        payload = CommercialEvaluationPayload(
            source_opportunity_artifact_id=opportunity.artifact_id,
            source_technical_artifact_id=technical.artifact_id,
            source_verification_artifact_id=verification.artifact_id,
            opportunity_ids=selected,
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            user_value=user_value,
            business_model=business_model,
            delivery_operations=delivery,
            business_hypotheses=output.business_hypotheses,
            commercial_gaps=gaps,
            recommendation=recommendation,
            recommendation_reason=reason,
            coverage=CommercialEvaluationCoverage(
                opportunity_count=len(selected),
                user_value_claim_count=len(user_value.claims),
                business_claim_count=len(business_model.claims),
                hypothesis_count=len(output.business_hypotheses),
                gap_count=len(gaps),
                evidence_context_hash=(
                    context.evidence_context.context_hash
                    if context.evidence_context is not None
                    else "0" * 64
                ),
            ),
        )
        unknowns = list(
            dict.fromkeys([*output.unknowns, *(item.question for item in gaps)])
        )
        return CommercialEvaluationArtifact(
            artifact_id=f"artifact_{task.task_id}_{context.iteration + 1}",
            task_id=task.task_id,
            status=(
                ResearchTaskStatus.PARTIAL
                if recommendation
                in {
                    CommercialRecommendation.CONDITIONAL,
                    CommercialRecommendation.NEEDS_MORE_EVIDENCE,
                }
                else ResearchTaskStatus.COMPLETED
            ),
            payload=payload,
            evidence_ids=sorted({*cited, *technical.evidence_ids, *verification.evidence_ids}),
            unknowns=unknowns,
            quality_score=max(0.0, round(100 - len(gaps) * 5, 2)),
        )

    def _dimension(
        self, name: str, intent: CommercialDimensionIntent
    ) -> CommercialDimensionConclusion:
        claims = [
            CommercialClaim(
                claim_id=commercial_claim_id(name, item.claim, item.evidence_ids),
                **item.model_dump(mode="python"),
            )
            for item in intent.claims
        ]
        computed = max(
            (item.status for item in claims), key=lambda item: _STATUS_ORDER[item]
        )
        if intent.status is not computed:
            raise self._error(
                "Dimension status must match its least-supported claim.",
                dimension=name,
                declared_status=intent.status.value,
                computed_status=computed.value,
            )
        return CommercialDimensionConclusion(
            status=computed,
            conclusion=intent.conclusion,
            claims=claims,
            assumptions=intent.assumptions,
        )

    @staticmethod
    def _delivery(
        technical: TechnicalFeasibilityArtifact,
        verification: PolicyVerificationArtifact,
        selected: list[str],
    ) -> DeliveryOperationsConclusion:
        assessments = {
            item.opportunity_id: item for item in technical.payload.assessments
        }
        conditional = [
            opportunity_id
            for opportunity_id in selected
            if assessments[opportunity_id].verdict
            is TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE
        ]
        failed_scenarios = [
            item.scenario_id
            for item in verification.payload.results
            if item.status is VerificationStatus.FAILED
        ]
        is_conditional = bool(
            conditional
            or verification.payload.verification_status
            is VerificationStatus.CONDITIONALLY_PASSED
            or verification.payload.validation_gaps
        )
        prerequisites = list(
            dict.fromkeys(
                item
                for opportunity_id in selected
                for item in [
                    *assessments[opportunity_id].gate_issues,
                    *assessments[opportunity_id].limitations,
                ]
            )
        )
        return DeliveryOperationsConclusion(
            status=(
                CommercialConclusionStatus.CONDITIONAL
                if is_conditional
                else CommercialConclusionStatus.SUPPORTED
            ),
            conclusion=(
                "技术与 dry-run 验证存在明确前置条件，交付只能按限制范围试点。"
                if is_conditional
                else "技术与 dry-run 验证支持进入受控试点准备。"
            ),
            technical_artifact_id=technical.artifact_id,
            verification_artifact_id=verification.artifact_id,
            conditional_opportunity_ids=conditional,
            failed_scenario_ids=failed_scenarios,
            prerequisites=prerequisites,
            evidence_ids=sorted({*technical.evidence_ids, *verification.evidence_ids}),
        )

    @staticmethod
    def _recommendation(
        user: CommercialConclusionStatus,
        business: CommercialConclusionStatus,
        delivery: CommercialConclusionStatus,
        has_gaps: bool,
    ) -> CommercialRecommendation:
        statuses = {user, business, delivery}
        if CommercialConclusionStatus.UNSUPPORTED in statuses:
            return CommercialRecommendation.DO_NOT_RECOMMEND
        if CommercialConclusionStatus.INSUFFICIENT_EVIDENCE in statuses or has_gaps:
            return CommercialRecommendation.NEEDS_MORE_EVIDENCE
        if CommercialConclusionStatus.CONDITIONAL in statuses:
            return CommercialRecommendation.CONDITIONAL
        return CommercialRecommendation.RECOMMEND_FOR_VALIDATION

    @staticmethod
    def _recommendation_reason(
        recommendation: CommercialRecommendation,
        user: CommercialConclusionStatus,
        business: CommercialConclusionStatus,
        delivery: CommercialConclusionStatus,
    ) -> str:
        return (
            f"结论={recommendation.value}；用户价值={user.value}；"
            f"商业模式={business.value}；交付运营={delivery.value}。"
            "该结论只决定是否继续验证，不代表正式上架或保证收益。"
        )

    @staticmethod
    def _allowed_evidence(
        context: AgentContext,
        *artifacts: (
            UserResearchArtifact
            | EcosystemOpportunityArtifact
            | TechnicalFeasibilityArtifact
            | PolicyVerificationArtifact
        ),
    ) -> set[str]:
        return {
            *(
                item.evidence_id
                for item in (
                    context.evidence_context.items
                    if context.evidence_context is not None
                    else []
                )
            ),
            *(evidence_id for artifact in artifacts for evidence_id in artifact.evidence_ids),
        }

    @staticmethod
    def _cited_evidence(output: CommercialEvaluationModelOutput) -> set[str]:
        return {
            *output.summary_evidence_ids,
            *(
                evidence_id
                for dimension in (output.user_value, output.business_model)
                for claim in dimension.claims
                for evidence_id in claim.evidence_ids
            ),
            *(
                evidence_id
                for hypothesis in output.business_hypotheses
                for evidence_id in hypothesis.evidence_ids
            ),
        }

    @staticmethod
    def _artifact(context: AgentContext, agent_type: str) -> ResearchArtifact:
        raw = context.upstream_artifacts.get(agent_type)
        if raw is None:
            raise CommercialEvaluationValidationError(
                f"Commercial Evaluation requires {agent_type}.", {}
            )
        return raw

    @classmethod
    def _user_artifact(cls, context: AgentContext) -> UserResearchArtifact:
        return UserResearchArtifact.from_research_artifact(
            cls._artifact(context, "user_research")
        )

    @classmethod
    def _opportunity_artifact(cls, context: AgentContext) -> EcosystemOpportunityArtifact:
        return EcosystemOpportunityArtifact.from_research_artifact(
            cls._artifact(context, "ecosystem_opportunity")
        )

    @classmethod
    def _technical_artifact(cls, context: AgentContext) -> TechnicalFeasibilityArtifact:
        return TechnicalFeasibilityArtifact.from_research_artifact(
            cls._artifact(context, "technical_feasibility")
        )

    @classmethod
    def _verification_artifact(cls, context: AgentContext) -> PolicyVerificationArtifact:
        return PolicyVerificationArtifact.from_research_artifact(
            cls._artifact(context, "policy_verification")
        )

    @staticmethod
    def _error(
        message: str, **details: object
    ) -> CommercialEvaluationValidationError:
        return CommercialEvaluationValidationError(message, details)
