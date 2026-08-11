"""Deterministic feasibility verdicts over model analysis and capability facts."""

from __future__ import annotations

import re

from app.agents.ecosystem_opportunity import (
    DeviceCapabilityGraphContext,
    EcosystemGateStatus,
    EcosystemOpportunityArtifact,
)
from app.agents.technical_feasibility.contracts import (
    CapabilityFeasibilityAssessment,
    TechnicalFeasibilityArtifact,
    TechnicalFeasibilityAssessment,
    TechnicalFeasibilityCoverage,
    TechnicalFeasibilityGap,
    TechnicalFeasibilityModelGap,
    TechnicalFeasibilityModelOutput,
    TechnicalFeasibilityPayload,
    TechnicalFeasibilityVerdict,
    TechnicalRequirementModel,
    TechnicalSupportStatus,
    technical_feasibility_gap_id,
)
from app.workflows.contracts import AgentContext, ResearchTask, ResearchTaskStatus


class TechnicalFeasibilityValidationError(ValueError):
    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__(message)


class TechnicalFeasibilityOutputValidator:
    def validate(
        self,
        task: ResearchTask,
        context: AgentContext,
        graph: DeviceCapabilityGraphContext,
        output: TechnicalFeasibilityModelOutput,
    ) -> TechnicalFeasibilityArtifact:
        source = self._source_artifact(context)
        selected_ids = list(dict.fromkeys(context.selected_innovation_ids))
        if not selected_ids:
            raise TechnicalFeasibilityValidationError(
                "Technical Feasibility requires Human Gate selected opportunities."
            )
        opportunity_by_id = {
            item.opportunity_id: item for item in source.payload.opportunities
        }
        missing = sorted(set(selected_ids) - set(opportunity_by_id))
        if missing:
            raise TechnicalFeasibilityValidationError(
                "Selected opportunities do not exist in source Artifact.",
                {"missing_opportunity_ids": missing},
            )
        blocked = sorted(
            opportunity_id
            for opportunity_id in selected_ids
            if opportunity_by_id[opportunity_id].gate_status is not EcosystemGateStatus.PASSED
        )
        if blocked:
            raise TechnicalFeasibilityValidationError(
                "Selected opportunities did not pass the ecosystem evidence gate.",
                {"blocked_opportunity_ids": blocked},
            )
        model_ids = [item.opportunity_id for item in output.assessments]
        if set(model_ids) != set(selected_ids):
            raise TechnicalFeasibilityValidationError(
                "Model assessments must match Human Gate selected opportunities.",
                {"selected": selected_ids, "assessed": model_ids},
            )

        allowed_evidence = self._allowed_evidence(context, graph)
        self._validate_evidence(output, allowed_evidence)
        assessments: list[TechnicalFeasibilityAssessment] = []
        all_gaps: list[TechnicalFeasibilityGap] = [
            self._gap(item) for item in output.portfolio_gaps
        ]
        for model_assessment in output.assessments:
            opportunity = opportunity_by_id[model_assessment.opportunity_id]
            capabilities = list(
                dict.fromkeys(
                    [
                        *opportunity.ecosystem_blueprint.required_capabilities,
                        *(
                            capability
                            for role in opportunity.ecosystem_blueprint.required_device_roles
                            if not role.optional
                            for capability in role.required_capabilities
                        ),
                    ]
                )
            )
            capability_assessments = [
                self._assess_capability(capability, graph) for capability in capabilities
            ]
            source_requirements = [
                self._gap(item) for item in model_assessment.source_requirements
            ]
            for item in capability_assessments:
                if item.status in {
                    TechnicalSupportStatus.UNKNOWN,
                    TechnicalSupportStatus.UNSUPPORTED,
                    TechnicalSupportStatus.CONFLICT,
                }:
                    source_requirements.append(
                        self._capability_gap(
                            model_assessment.opportunity_id,
                            item.capability,
                            item.status,
                        )
                    )
            source_requirements = self._unique_gaps(source_requirements)
            verdict, issues = self._verdict(
                capability_assessments,
                model_assessment.requirements,
                source_requirements,
            )
            assessment = TechnicalFeasibilityAssessment(
                opportunity_id=model_assessment.opportunity_id,
                architecture_summary=model_assessment.architecture_summary,
                requirements=model_assessment.requirements,
                capability_assessments=capability_assessments,
                demo_scope=model_assessment.demo_scope,
                limitations=model_assessment.limitations,
                failure_modes=model_assessment.failure_modes,
                verdict=verdict,
                gate_issues=issues,
                source_requirements=source_requirements,
            )
            assessments.append(assessment)
            all_gaps.extend(source_requirements)

        all_gaps = self._unique_gaps(all_gaps)
        evidence_ids = sorted(
            {
                *output.summary_evidence_ids,
                *(
                    evidence_id
                    for assessment in assessments
                    for requirement in assessment.requirements
                    for evidence_id in requirement.evidence_ids
                ),
                *(
                    evidence_id
                    for assessment in assessments
                    for capability in assessment.capability_assessments
                    for evidence_id in capability.evidence_ids
                ),
            }
        )
        has_unknown = any(
            item.verdict is TechnicalFeasibilityVerdict.INSUFFICIENT_EVIDENCE
            for item in assessments
        )
        status = ResearchTaskStatus.PARTIAL if has_unknown else ResearchTaskStatus.COMPLETED
        coverage = TechnicalFeasibilityCoverage(
            selected_opportunity_count=len(selected_ids),
            assessed_opportunity_count=len(assessments),
            demo_feasible_count=self._count(
                assessments, TechnicalFeasibilityVerdict.DEMO_FEASIBLE
            ),
            conditionally_feasible_count=self._count(
                assessments, TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE
            ),
            insufficient_evidence_count=self._count(
                assessments, TechnicalFeasibilityVerdict.INSUFFICIENT_EVIDENCE
            ),
            not_feasible_count=self._count(
                assessments, TechnicalFeasibilityVerdict.NOT_FEASIBLE
            ),
            evidence_context_hash=(
                context.evidence_context.context_hash
                if context.evidence_context is not None
                else "0" * 64
            ),
            capability_graph_hash=graph.context_hash,
        )
        payload = TechnicalFeasibilityPayload(
            source_opportunity_artifact_id=source.artifact_id,
            selected_opportunity_ids=selected_ids,
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            assessments=assessments,
            portfolio_gaps=all_gaps,
            coverage=coverage,
        )
        return TechnicalFeasibilityArtifact(
            artifact_id=f"artifact_{task.task_id}_{context.iteration + 1}",
            task_id=task.task_id,
            status=status,
            payload=payload,
            evidence_ids=evidence_ids,
            contradictions=[
                issue
                for assessment in assessments
                for capability in assessment.capability_assessments
                if capability.status is TechnicalSupportStatus.CONFLICT
                for issue in capability.issues
            ],
            unknowns=list(
                dict.fromkeys([*output.unknowns, *(gap.question for gap in all_gaps)])
            ),
            quality_score=self._quality_score(assessments),
            errors=(
                ["NO_DEMO_FEASIBLE_OR_CONDITIONAL_OPPORTUNITY"]
                if not any(
                    item.verdict
                    in {
                        TechnicalFeasibilityVerdict.DEMO_FEASIBLE,
                        TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE,
                    }
                    for item in assessments
                )
                else []
            ),
        )

    @staticmethod
    def _source_artifact(context: AgentContext) -> EcosystemOpportunityArtifact:
        raw = context.upstream_artifacts.get("ecosystem_opportunity")
        if raw is None:
            raise TechnicalFeasibilityValidationError(
                "Technical Feasibility requires an Ecosystem Opportunity Artifact."
            )
        return EcosystemOpportunityArtifact.from_research_artifact(raw)

    @staticmethod
    def _allowed_evidence(
        context: AgentContext, graph: DeviceCapabilityGraphContext
    ) -> set[str]:
        return {
            *(
                item.evidence_id
                for item in (
                    context.evidence_context.items
                    if context.evidence_context
                    else []
                )
            ),
            *graph.evidence_ids,
        }

    @staticmethod
    def _validate_evidence(
        output: TechnicalFeasibilityModelOutput, allowed: set[str]
    ) -> None:
        cited = {
            *output.summary_evidence_ids,
            *(
                evidence_id
                for assessment in output.assessments
                for requirement in assessment.requirements
                for evidence_id in requirement.evidence_ids
            ),
        }
        unsupported = sorted(cited - allowed)
        if unsupported:
            raise TechnicalFeasibilityValidationError(
                "Technical Feasibility output cites Evidence outside the bounded context.",
                {"unsupported_evidence_ids": unsupported},
            )

    @classmethod
    def _assess_capability(
        cls, capability: str, graph: DeviceCapabilityGraphContext
    ) -> CapabilityFeasibilityAssessment:
        normalized = cls._normalize(capability)
        facts = [
            fact
            for fact in graph.facts
            if normalized
            in {cls._normalize(fact.capability_key), cls._normalize(fact.capability_name)}
        ]
        if not facts:
            return CapabilityFeasibilityAssessment(
                capability=capability,
                status=TechnicalSupportStatus.UNKNOWN,
                issues=["capability_not_found_in_device_graph"],
            )
        supported = [
            fact
            for fact in facts
            if fact.assertion == "supported" and fact.availability == "available"
        ]
        negative = [
            fact
            for fact in facts
            if fact.assertion == "unsupported" or fact.availability == "unavailable"
        ]
        evidence_ids = list(
            dict.fromkeys(
                evidence_id for fact in facts for evidence_id in fact.evidence_ids
            )
        )
        device_ids = list(dict.fromkeys(fact.catalog_device_id for fact in facts))
        if supported and negative:
            status = TechnicalSupportStatus.CONFLICT
            issues = ["device_capability_evidence_conflict"]
        elif negative and not supported:
            status = TechnicalSupportStatus.UNSUPPORTED
            issues = ["required_capability_unavailable"]
        elif not supported:
            status = TechnicalSupportStatus.UNKNOWN
            issues = ["required_capability_not_confirmed_available"]
        elif any(
            fact.authorization_required
            or fact.lifecycle_status != "active"
            or fact.offline_support in {"degraded", "none", "unknown"}
            for fact in supported
        ):
            status = TechnicalSupportStatus.CONDITIONAL
            issues = ["capability_requires_authorization_or_degraded_operation"]
        else:
            status = TechnicalSupportStatus.SUPPORTED
            issues = []
        return CapabilityFeasibilityAssessment(
            capability=capability,
            status=status,
            matched_device_ids=device_ids,
            evidence_ids=evidence_ids,
            issues=issues,
        )

    @staticmethod
    def _verdict(
        capabilities: list[CapabilityFeasibilityAssessment],
        requirements: list[TechnicalRequirementModel],
        gaps: list[TechnicalFeasibilityGap],
    ) -> tuple[TechnicalFeasibilityVerdict, list[str]]:
        requirement_statuses = {item.status for item in requirements}
        capability_statuses = {item.status for item in capabilities}
        statuses = requirement_statuses | capability_statuses
        issues = list(
            dict.fromkeys(
                [
                    *(issue for item in capabilities for issue in item.issues),
                    *("technical_source_requirement_unresolved" for _ in gaps),
                ]
            )
        )
        if statuses.intersection(
            {TechnicalSupportStatus.UNSUPPORTED, TechnicalSupportStatus.CONFLICT}
        ):
            return TechnicalFeasibilityVerdict.NOT_FEASIBLE, issues
        if TechnicalSupportStatus.UNKNOWN in statuses or gaps:
            return TechnicalFeasibilityVerdict.INSUFFICIENT_EVIDENCE, issues
        if TechnicalSupportStatus.CONDITIONAL in statuses:
            return TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE, issues
        return TechnicalFeasibilityVerdict.DEMO_FEASIBLE, issues

    @staticmethod
    def _gap(item: TechnicalFeasibilityModelGap) -> TechnicalFeasibilityGap:
        return TechnicalFeasibilityGap(
            gap_id=technical_feasibility_gap_id(
                item.question, item.affected_opportunity_ids
            ),
            **item.model_dump(mode="python"),
        )

    @staticmethod
    def _capability_gap(
        opportunity_id: str,
        capability: str,
        status: TechnicalSupportStatus,
    ) -> TechnicalFeasibilityGap:
        question = f"哪些设备/API 文档或内部测试能够确认“{capability}”的真实可用性？"
        return TechnicalFeasibilityGap(
            gap_id=technical_feasibility_gap_id(question, [opportunity_id]),
            question=question,
            reason=f"所选生态机会依赖该能力，当前设备能力图状态为 {status.value}。",
            required_evidence_types=[
                "device_capability",
                "api_documentation",
                "internal_test_result",
            ],
            affected_opportunity_ids=[opportunity_id],
        )

    @staticmethod
    def _unique_gaps(
        gaps: list[TechnicalFeasibilityGap],
    ) -> list[TechnicalFeasibilityGap]:
        by_id: dict[str, TechnicalFeasibilityGap] = {}
        for gap in gaps:
            by_id.setdefault(gap.gap_id, gap)
        return list(by_id.values())

    @staticmethod
    def _count(
        assessments: list[TechnicalFeasibilityAssessment],
        verdict: TechnicalFeasibilityVerdict,
    ) -> int:
        return sum(item.verdict is verdict for item in assessments)

    @staticmethod
    def _quality_score(assessments: list[TechnicalFeasibilityAssessment]) -> float:
        if not assessments:
            return 0.0
        resolved = sum(
            item.verdict is not TechnicalFeasibilityVerdict.INSUFFICIENT_EVIDENCE
            for item in assessments
        )
        return round(40 + 60 * resolved / len(assessments), 2)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\w]+", "", value.casefold())
