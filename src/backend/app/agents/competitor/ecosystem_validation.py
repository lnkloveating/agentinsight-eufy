"""Deterministic scope, evidence and coverage audit for ecosystem synthesis v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.competitor.ecosystem_contracts import (
    CompetitorEcosystemEvidenceAudit,
    CompetitorEcosystemModelOutput,
    CompetitorEcosystemPayload,
    CompetitorEcosystemProfile,
    EcosystemCapabilityAssessment,
    EcosystemCapabilityDimension,
    EcosystemCapabilityStatus,
    EcosystemDimensionCoverage,
    EcosystemDiscoveryProjection,
    EcosystemGapSeverity,
    EcosystemResearchGap,
    EcosystemRole,
)
from app.integrations.a2a import CompetitorSpecialistArtifact, CompetitorSpecialistType
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTaskStatus,
)


@dataclass(frozen=True)
class CompetitorEcosystemValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class CompetitorEcosystemOutputValidator:
    def validate(
        self,
        *,
        artifact_id: str,
        task_id: str,
        target_ecosystems: list[str],
        comparison_ecosystems: list[str],
        product_scope: list[str],
        specialist_artifacts: list[CompetitorSpecialistArtifact],
        product_fact_synthesis: ResearchArtifact,
        evidence_context: AgentEvidenceContext,
        output: CompetitorEcosystemModelOutput,
    ) -> ResearchArtifact:
        requested_roles = {
            **{label: EcosystemRole.TARGET for label in target_ecosystems},
            **{label: EcosystemRole.COMPARISON for label in comparison_ecosystems},
        }
        requested = set(requested_roles)
        evidence_by_id = {item.evidence_id: item for item in evidence_context.items}
        specialist_types = [
            artifact.specialist_type for artifact in specialist_artifacts
        ]
        expected_specialists = set(CompetitorSpecialistType)
        if len(specialist_types) != len(expected_specialists) or set(
            specialist_types
        ) != expected_specialists:
            raise CompetitorEcosystemValidationError(
                "Ecosystem synthesis requires exactly one output from each fact specialist.",
                {
                    "specialist_types": sorted(
                        specialist.value for specialist in specialist_types
                    )
                },
            )
        specialist_by_dimension = {
            artifact.specialist_type.value: set(artifact.evidence_ids)
            for artifact in specialist_artifacts
        }
        allowed = set().union(*specialist_by_dimension.values())
        if missing := sorted(allowed - set(evidence_by_id)):
            raise CompetitorEcosystemValidationError(
                "Ecosystem synthesis specialist Evidence is absent from parent context.",
                {"missing_context_evidence_ids": missing},
            )
        if unsupported_product_facts := sorted(
            set(product_fact_synthesis.evidence_ids) - allowed
        ):
            raise CompetitorEcosystemValidationError(
                "Product fact synthesis escaped the specialist Evidence boundary.",
                {"unsupported_evidence_ids": unsupported_product_facts},
            )
        if unsupported := sorted(output.cited_evidence_ids() - allowed):
            raise CompetitorEcosystemValidationError(
                "Ecosystem synthesis cited Evidence outside specialist outputs.",
                {"unsupported_evidence_ids": unsupported},
            )

        profiles = {profile.ecosystem_label: profile for profile in output.ecosystem_profiles}
        if unexpected := sorted(set(profiles) - requested):
            raise CompetitorEcosystemValidationError(
                "Ecosystem synthesis contains an ecosystem outside the Research Brief.",
                {"unexpected_ecosystems": unexpected},
            )
        if wrong_roles := sorted(
            label
            for label, profile in profiles.items()
            if profile.role is not requested_roles[label]
        ):
            raise CompetitorEcosystemValidationError(
                "Ecosystem role does not match the Research Brief.",
                {"wrong_role_ecosystems": wrong_roles},
            )

        requested_products = set(product_scope)
        product_owners: dict[str, str] = {}
        for profile in output.ecosystem_profiles:
            if unknown_products := sorted(
                set(profile.product_scope_labels) - requested_products
            ):
                raise CompetitorEcosystemValidationError(
                    "Ecosystem profile mapped a product outside confirmed scope.",
                    {
                        "ecosystem_label": profile.ecosystem_label,
                        "unknown_product_scope_labels": unknown_products,
                    },
                )
            for product in profile.product_scope_labels:
                owner = product_owners.setdefault(product, profile.ecosystem_label)
                if owner != profile.ecosystem_label:
                    raise CompetitorEcosystemValidationError(
                        "One product cannot be mapped to multiple ecosystems.",
                        {"product": product, "ecosystems": [owner, profile.ecosystem_label]},
                    )
            for assessment in profile.assessments:
                self._validate_assessment(
                    ecosystem_label=profile.ecosystem_label,
                    mapped_products=set(profile.product_scope_labels),
                    assessment=assessment,
                    evidence_by_id=evidence_by_id,
                    specialist_by_dimension=specialist_by_dimension,
                )

        for insight in output.comparison_insights:
            self._validate_cross_ecosystem_item(
                item_id=insight.insight_id,
                ecosystem_labels=insight.ecosystem_labels,
                evidence_ids=insight.evidence_ids,
                requested=requested,
                profiles=profiles,
                evidence_by_id=evidence_by_id,
            )
        for signal in output.opportunity_signals:
            self._validate_cross_ecosystem_item(
                item_id=signal.signal_id,
                ecosystem_labels=signal.ecosystem_labels,
                evidence_ids=signal.evidence_ids,
                requested=requested,
                profiles=profiles,
                evidence_by_id=evidence_by_id,
            )
        if unexpected_gaps := sorted(
            {gap.ecosystem_label for gap in output.research_gaps} - requested
        ):
            raise CompetitorEcosystemValidationError(
                "Ecosystem research gap is outside the Research Brief.",
                {"unexpected_gap_ecosystems": unexpected_gaps},
            )

        coverage = self._coverage_matrix(
            list(requested_roles), profiles, evidence_by_id
        )
        research_gaps = self._complete_research_gaps(
            coverage=coverage,
            profiles=profiles,
            model_gaps=output.research_gaps,
        )
        complete = (
            bool(requested)
            and len(profiles) == len(requested)
            and all(row.complete for row in coverage)
            and len(specialist_artifacts) == 3
            and all(
                artifact.status is ResearchTaskStatus.COMPLETED
                for artifact in specialist_artifacts
            )
            and not any(
                gap.severity is EcosystemGapSeverity.HIGH
                for gap in research_gaps
            )
        )
        cited = output.cited_evidence_ids()
        unknown_count = sum(row.unknown_dimension_count for row in coverage)
        evidence_backed_count = sum(
            row.evidence_backed_dimension_count for row in coverage
        )
        audit = CompetitorEcosystemEvidenceAudit(
            status="passed" if complete else "passed_with_gaps",
            allowed_evidence_count=len(allowed),
            cited_evidence_count=len(cited),
            specialist_output_count=len(specialist_artifacts),
            requested_ecosystem_count=len(requested),
            represented_ecosystem_count=len(profiles),
            mapped_product_count=len(product_owners),
            evidence_backed_dimension_count=evidence_backed_count,
            unknown_dimension_count=unknown_count,
            independent_source_count=len(
                self._independent_sources(cited, evidence_by_id)
            ),
            evidence_context_hash=evidence_context.context_hash,
        )
        discovery = EcosystemDiscoveryProjection(
            target_ecosystems=target_ecosystems,
            comparison_ecosystems=comparison_ecosystems,
            confirmed_product_scope=product_scope,
            represented_ecosystems=list(profiles),
            unmapped_products=sorted(requested_products - set(product_owners)),
        )
        payload = CompetitorEcosystemPayload(
            specialist_outputs=[
                artifact.model_dump(mode="json") for artifact in specialist_artifacts
            ],
            product_fact_synthesis=product_fact_synthesis.payload,
            discovery=discovery,
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            ecosystem_profiles=output.ecosystem_profiles,
            comparison_insights=output.comparison_insights,
            opportunity_signals=output.opportunity_signals,
            research_gaps=research_gaps,
            coverage_matrix=coverage,
            evidence_audit=audit,
            synthesis_status="completed" if complete else "partial",
        )
        unknowns = list(
            dict.fromkeys(
                [
                    *(unknown for item in specialist_artifacts for unknown in item.unknowns),
                    *output.unknowns,
                    *(gap.question for gap in research_gaps),
                    *(
                        f"No confirmed ecosystem mapping for product: {product}"
                        for product in discovery.unmapped_products
                    ),
                ]
            )
        )
        average_quality = sum(
            artifact.quality_score for artifact in specialist_artifacts
        ) / max(len(specialist_artifacts), 1)
        dimension_total = max(len(requested) * len(EcosystemCapabilityDimension), 1)
        coverage_ratio = evidence_backed_count / dimension_total
        quality_score = round(min(100.0, average_quality * 0.7 + coverage_ratio * 30), 2)
        return ResearchArtifact(
            artifact_id=artifact_id,
            task_id=task_id,
            artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
            schema_version="2.0",
            status=(
                ResearchTaskStatus.COMPLETED
                if complete
                else ResearchTaskStatus.PARTIAL
            ),
            payload=payload.model_dump(mode="json"),
            evidence_ids=sorted(allowed),
            unknowns=unknowns,
            quality_score=quality_score,
            errors=[],
        )

    @staticmethod
    def _validate_assessment(
        *,
        ecosystem_label: str,
        mapped_products: set[str],
        assessment: EcosystemCapabilityAssessment,
        evidence_by_id: dict[str, AgentEvidence],
        specialist_by_dimension: dict[str, set[str]],
    ) -> None:
        if assessment.status is EcosystemCapabilityStatus.UNKNOWN:
            return
        permitted = set().union(
            *(
                specialist_by_dimension.get(dimension.value, set())
                for dimension in assessment.source_dimensions
            )
        )
        if wrong_source := sorted(set(assessment.evidence_ids) - permitted):
            raise CompetitorEcosystemValidationError(
                "Ecosystem assessment crossed a specialist Evidence boundary.",
                {
                    "assessment_id": assessment.assessment_id,
                    "wrong_source_evidence_ids": wrong_source,
                },
            )
        if not mapped_products:
            raise CompetitorEcosystemValidationError(
                "Evidence-backed ecosystem assessment requires a confirmed product mapping.",
                {"ecosystem_label": ecosystem_label, "assessment_id": assessment.assessment_id},
            )
        if wrong_product := sorted(
            evidence_id
            for evidence_id in assessment.evidence_ids
            if evidence_by_id[evidence_id].product not in mapped_products
        ):
            raise CompetitorEcosystemValidationError(
                "Ecosystem assessment cited Evidence from a product mapped elsewhere.",
                {
                    "assessment_id": assessment.assessment_id,
                    "wrong_product_evidence_ids": wrong_product,
                },
            )

    @staticmethod
    def _validate_cross_ecosystem_item(
        *,
        item_id: str,
        ecosystem_labels: list[str],
        evidence_ids: list[str],
        requested: set[str],
        profiles: dict[str, CompetitorEcosystemProfile],
        evidence_by_id: dict[str, AgentEvidence],
    ) -> None:
        if unexpected := sorted(set(ecosystem_labels) - requested):
            raise CompetitorEcosystemValidationError(
                "Cross-ecosystem item contains an ecosystem outside the Research Brief.",
                {"item_id": item_id, "unexpected_ecosystems": unexpected},
            )
        mapped_products = {
            product
            for label in ecosystem_labels
            if label in profiles
            for product in profiles[label].product_scope_labels
        }
        if wrong_product := sorted(
            evidence_id
            for evidence_id in evidence_ids
            if evidence_by_id[evidence_id].product not in mapped_products
        ):
            raise CompetitorEcosystemValidationError(
                "Cross-ecosystem item cited Evidence outside represented ecosystems.",
                {"item_id": item_id, "wrong_product_evidence_ids": wrong_product},
            )

    @staticmethod
    def _coverage_matrix(
        ecosystem_scope: list[str],
        profiles: dict[str, CompetitorEcosystemProfile],
        evidence_by_id: dict[str, AgentEvidence],
    ) -> list[EcosystemDimensionCoverage]:
        rows: list[EcosystemDimensionCoverage] = []
        for label in ecosystem_scope:
            profile = profiles.get(label)
            assessments = (
                {item.dimension: item for item in profile.assessments}
                if profile is not None
                else {}
            )
            statuses = {
                dimension: (
                    assessments[dimension].status
                    if dimension in assessments
                    else EcosystemCapabilityStatus.UNKNOWN
                )
                for dimension in EcosystemCapabilityDimension
            }
            evidence_ids = sorted(
                {
                    evidence_id
                    for assessment in assessments.values()
                    for evidence_id in assessment.evidence_ids
                    if evidence_id in evidence_by_id
                }
            )
            evidence_backed = sum(
                status is not EcosystemCapabilityStatus.UNKNOWN
                for status in statuses.values()
            )
            unknown = len(statuses) - evidence_backed
            rows.append(
                EcosystemDimensionCoverage(
                    ecosystem_label=label,
                    dimension_statuses=statuses,
                    mapped_products=(profile.product_scope_labels if profile else []),
                    evidence_ids=evidence_ids,
                    evidence_backed_dimension_count=evidence_backed,
                    unknown_dimension_count=unknown,
                    complete=unknown == 0,
                )
            )
        return rows

    @staticmethod
    def _independent_sources(
        evidence_ids: set[str], evidence_by_id: dict[str, AgentEvidence]
    ) -> set[str]:
        sources: set[str] = set()
        for evidence_id in evidence_ids:
            item = evidence_by_id[evidence_id]
            if item.source_domain:
                sources.add(f"domain:{item.source_domain}")
            elif item.source_asset_id:
                sources.add(f"asset:{item.source_asset_id}")
            else:
                sources.add(f"source_type:{item.source_type}")
        return sources

    @staticmethod
    def _complete_research_gaps(
        *,
        coverage: list[EcosystemDimensionCoverage],
        profiles: dict[str, CompetitorEcosystemProfile],
        model_gaps: list[EcosystemResearchGap],
    ) -> list[EcosystemResearchGap]:
        gaps = list(model_gaps)
        existing = {(gap.ecosystem_label, gap.dimension) for gap in gaps}
        for row in coverage:
            profile = profiles.get(row.ecosystem_label)
            assessments = (
                {item.dimension: item for item in profile.assessments}
                if profile is not None
                else {}
            )
            for dimension, status in row.dimension_statuses.items():
                key = (row.ecosystem_label, dimension)
                if status is not EcosystemCapabilityStatus.UNKNOWN or key in existing:
                    continue
                assessment = assessments.get(dimension)
                reason = (
                    assessment.unknown_reason
                    if assessment is not None and assessment.unknown_reason is not None
                    else "No evidence-backed assessment covers this ecosystem dimension."
                )
                gaps.append(
                    EcosystemResearchGap(
                        ecosystem_label=row.ecosystem_label,
                        dimension=dimension,
                        question=(
                            f"What evidence establishes {dimension.value} for "
                            f"{row.ecosystem_label}?"
                        ),
                        reason=reason,
                        severity=EcosystemGapSeverity.MEDIUM,
                    )
                )
                existing.add(key)
        return gaps


def build_blocked_ecosystem_artifact(
    *,
    artifact_id: str,
    task_id: str,
    target_ecosystems: list[str],
    comparison_ecosystems: list[str],
    product_scope: list[str],
    specialist_artifacts: list[CompetitorSpecialistArtifact],
    evidence_context: AgentEvidenceContext,
    reason: str,
) -> ResearchArtifact:
    ecosystem_scope = [*target_ecosystems, *comparison_ecosystems]
    coverage = CompetitorEcosystemOutputValidator._coverage_matrix(
        ecosystem_scope, {}, {item.evidence_id: item for item in evidence_context.items}
    )
    allowed = sorted(
        {
            evidence_id
            for artifact in specialist_artifacts
            for evidence_id in artifact.evidence_ids
        }
    )
    gaps = [
        EcosystemResearchGap(
            ecosystem_label=label,
            dimension=dimension,
            question=f"What evidence establishes {dimension.value} for {label}?",
            reason=reason,
            severity=EcosystemGapSeverity.HIGH,
        )
        for label in ecosystem_scope
        for dimension in EcosystemCapabilityDimension
    ]
    payload = CompetitorEcosystemPayload(
        specialist_outputs=[
            artifact.model_dump(mode="json") for artifact in specialist_artifacts
        ],
        discovery=EcosystemDiscoveryProjection(
            target_ecosystems=target_ecosystems,
            comparison_ecosystems=comparison_ecosystems,
            confirmed_product_scope=product_scope,
            represented_ecosystems=[],
            unmapped_products=product_scope,
        ),
        summary="竞品生态资料不足，尚不能执行有证据约束的生态综合。",
        summary_evidence_ids=[],
        ecosystem_profiles=[],
        comparison_insights=[],
        opportunity_signals=[],
        research_gaps=gaps,
        coverage_matrix=coverage,
        evidence_audit=CompetitorEcosystemEvidenceAudit(
            status="passed_with_gaps",
            allowed_evidence_count=len(allowed),
            cited_evidence_count=0,
            specialist_output_count=len(specialist_artifacts),
            requested_ecosystem_count=len(ecosystem_scope),
            represented_ecosystem_count=0,
            mapped_product_count=0,
            evidence_backed_dimension_count=0,
            unknown_dimension_count=len(ecosystem_scope)
            * len(EcosystemCapabilityDimension),
            independent_source_count=0,
            evidence_context_hash=evidence_context.context_hash,
        ),
        synthesis_status="blocked",
    )
    return ResearchArtifact(
        artifact_id=artifact_id,
        task_id=task_id,
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        schema_version="2.0",
        status=ResearchTaskStatus.BLOCKED,
        payload=payload.model_dump(mode="json"),
        evidence_ids=allowed,
        unknowns=[reason],
        quality_score=0,
        errors=[],
    )
