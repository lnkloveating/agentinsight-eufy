"""Deterministic scope, lineage and specialist-boundary audit for synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.competitor.synthesis_contracts import (
    CompetitorEvidenceAudit,
    CompetitorSynthesisModelOutput,
    CompetitorSynthesisPayload,
    ProductAssessmentPoint,
    ProductDimensionCoverage,
    SynthesisDimension,
    SynthesisGapSeverity,
)
from app.integrations.a2a import (
    CompetitorSpecialistArtifact,
    CompetitorSpecialistType,
    EvidenceRequest,
)
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTaskStatus,
)


@dataclass(frozen=True)
class CompetitorSynthesisValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class CompetitorSynthesisOutputValidator:
    def validate(
        self,
        *,
        artifact_id: str,
        task_id: str,
        product_scope: list[str],
        requests: list[EvidenceRequest],
        specialist_artifacts: list[CompetitorSpecialistArtifact],
        evidence_context: AgentEvidenceContext,
        output: CompetitorSynthesisModelOutput,
    ) -> ResearchArtifact:
        requested = set(product_scope)
        request_specialists = {request.specialist_type for request in requests}
        artifact_specialists = {
            artifact.specialist_type for artifact in specialist_artifacts
        }
        if request_specialists != artifact_specialists:
            raise CompetitorSynthesisValidationError(
                "Synthesis specialist artifacts do not match dispatched requests.",
                {
                    "request_specialists": sorted(item.value for item in request_specialists),
                    "artifact_specialists": sorted(
                        item.value for item in artifact_specialists
                    ),
                },
            )
        mismatched_request_scope = sorted(
            request.request_id
            for request in requests
            if set(request.product_scope) != requested
        )
        if mismatched_request_scope:
            raise CompetitorSynthesisValidationError(
                "Synthesis received inconsistent product scopes from specialist requests.",
                {"mismatched_request_ids": mismatched_request_scope},
            )
        evidence_by_id = {item.evidence_id: item for item in evidence_context.items}
        specialist_by_dimension = {
            artifact.specialist_type.value: set(artifact.evidence_ids)
            for artifact in specialist_artifacts
        }
        allowed = set().union(*specialist_by_dimension.values())
        missing_from_context = sorted(allowed - set(evidence_by_id))
        if missing_from_context:
            raise CompetitorSynthesisValidationError(
                "Specialist output references Evidence absent from the parent context.",
                {"missing_context_evidence_ids": missing_from_context},
            )
        cited = output.cited_evidence_ids()
        unsupported = sorted(cited - allowed)
        if unsupported:
            raise CompetitorSynthesisValidationError(
                "Competitor synthesis cited Evidence outside specialist outputs.",
                {"unsupported_evidence_ids": unsupported},
            )

        profile_labels = {profile.scope_label for profile in output.product_profiles}
        represented_labels = {
            *profile_labels,
            *(label for item in output.comparative_insights for label in item.scope_labels),
            *(label for item in output.opportunity_signals for label in item.scope_labels),
            *(gap.scope_label for gap in output.research_gaps),
        }
        unexpected = sorted(represented_labels - requested)
        if unexpected:
            raise CompetitorSynthesisValidationError(
                "Competitor synthesis contains products outside the confirmed scope.",
                {"unexpected_scope_labels": unexpected},
            )

        for profile in output.product_profiles:
            for point in [*profile.strengths, *profile.weaknesses, *profile.tradeoffs]:
                self._validate_point(
                    point,
                    scope_labels={profile.scope_label},
                    evidence_by_id=evidence_by_id,
                    specialist_by_dimension=specialist_by_dimension,
                )
        for insight in output.comparative_insights:
            self._validate_cited_item(
                item_id=insight.insight_id,
                dimension=insight.dimension,
                evidence_ids=insight.evidence_ids,
                scope_labels=set(insight.scope_labels),
                evidence_by_id=evidence_by_id,
                specialist_by_dimension=specialist_by_dimension,
            )
        for signal in output.opportunity_signals:
            self._validate_cited_item(
                item_id=signal.signal_id,
                dimension=SynthesisDimension.CROSS_DIMENSION,
                evidence_ids=signal.evidence_ids,
                scope_labels=set(signal.scope_labels),
                evidence_by_id=evidence_by_id,
                specialist_by_dimension=specialist_by_dimension,
            )

        coverage = self._coverage_matrix(
            product_scope, specialist_by_dimension, evidence_by_id
        )
        complete_products = sum(item.complete for item in coverage)
        high_gap = any(
            gap.severity is SynthesisGapSeverity.HIGH for gap in output.research_gaps
        )
        all_specialists_completed = len(specialist_artifacts) == 3 and all(
            artifact.status is ResearchTaskStatus.COMPLETED
            for artifact in specialist_artifacts
        )
        completed = (
            bool(product_scope)
            and profile_labels == requested
            and complete_products == len(product_scope)
            and all_specialists_completed
            and not high_gap
        )
        status = ResearchTaskStatus.COMPLETED if completed else ResearchTaskStatus.PARTIAL
        sources = self._independent_sources(cited, evidence_by_id)
        audit = CompetitorEvidenceAudit(
            status="passed" if completed else "passed_with_gaps",
            allowed_evidence_count=len(allowed),
            cited_evidence_count=len(cited),
            specialist_output_count=len(specialist_artifacts),
            requested_product_count=len(product_scope),
            represented_product_count=len(profile_labels),
            complete_product_count=complete_products,
            independent_source_count=len(sources),
            evidence_context_hash=evidence_context.context_hash,
        )
        payload = CompetitorSynthesisPayload(
            specialist_outputs=[
                artifact.model_dump(mode="json") for artifact in specialist_artifacts
            ],
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            product_profiles=output.product_profiles,
            comparative_insights=output.comparative_insights,
            opportunity_signals=output.opportunity_signals,
            research_gaps=output.research_gaps,
            coverage_matrix=coverage,
            evidence_audit=audit,
            synthesis_status="completed" if completed else "partial",
        )
        request_unknowns = [
            unknown for artifact in specialist_artifacts for unknown in artifact.unknowns
        ]
        unknowns = list(
            dict.fromkeys(
                [
                    *request_unknowns,
                    *output.unknowns,
                    *(gap.question for gap in output.research_gaps),
                ]
            )
        )
        average_specialist_quality = sum(
            artifact.quality_score for artifact in specialist_artifacts
        ) / max(len(specialist_artifacts), 1)
        coverage_ratio = complete_products / max(len(product_scope), 1)
        quality_score = round(
            min(100.0, average_specialist_quality * 0.7 + coverage_ratio * 30), 2
        )
        return ResearchArtifact(
            artifact_id=artifact_id,
            task_id=task_id,
            artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
            schema_version="1.0",
            status=status,
            payload=payload.model_dump(mode="json"),
            evidence_ids=sorted(cited),
            unknowns=unknowns,
            quality_score=quality_score,
            errors=[],
        )

    def _validate_point(
        self,
        point: ProductAssessmentPoint,
        *,
        scope_labels: set[str],
        evidence_by_id: dict[str, AgentEvidence],
        specialist_by_dimension: dict[str, set[str]],
    ) -> None:
        self._validate_cited_item(
            item_id=point.point_id,
            dimension=point.dimension,
            evidence_ids=point.evidence_ids,
            scope_labels=scope_labels,
            evidence_by_id=evidence_by_id,
            specialist_by_dimension=specialist_by_dimension,
        )

    @staticmethod
    def _validate_cited_item(
        *,
        item_id: str,
        dimension: SynthesisDimension,
        evidence_ids: list[str],
        scope_labels: set[str],
        evidence_by_id: dict[str, AgentEvidence],
        specialist_by_dimension: dict[str, set[str]],
    ) -> None:
        if dimension is not SynthesisDimension.CROSS_DIMENSION:
            permitted = specialist_by_dimension.get(dimension.value, set())
            wrong_dimension = sorted(set(evidence_ids) - permitted)
            if wrong_dimension:
                raise CompetitorSynthesisValidationError(
                    "Synthesis item crossed a specialist evidence boundary.",
                    {
                        "item_id": item_id,
                        "dimension": dimension.value,
                        "wrong_dimension_evidence_ids": wrong_dimension,
                    },
                )
        wrong_product = sorted(
            evidence_id
            for evidence_id in evidence_ids
            if evidence_by_id[evidence_id].product not in scope_labels
        )
        if wrong_product:
            raise CompetitorSynthesisValidationError(
                "Synthesis item cited Evidence from a different product.",
                {"item_id": item_id, "wrong_product_evidence_ids": wrong_product},
            )

    @staticmethod
    def _coverage_matrix(
        product_scope: list[str],
        specialist_by_dimension: dict[str, set[str]],
        evidence_by_id: dict[str, AgentEvidence],
    ) -> list[ProductDimensionCoverage]:
        rows: list[ProductDimensionCoverage] = []
        for product in product_scope:
            ids_by_dimension = {
                dimension: sorted(
                    evidence_id
                    for evidence_id in specialist_by_dimension.get(dimension, set())
                    if evidence_by_id[evidence_id].product == product
                )
                for dimension in (
                    CompetitorSpecialistType.OFFICIAL_PRODUCT.value,
                    CompetitorSpecialistType.PRICE_CHANNEL.value,
                    CompetitorSpecialistType.USER_REVIEW.value,
                )
            }
            rows.append(
                ProductDimensionCoverage(
                    scope_label=product,
                    official_product_evidence_ids=ids_by_dimension["official_product"],
                    price_channel_evidence_ids=ids_by_dimension["price_channel"],
                    user_review_evidence_ids=ids_by_dimension["user_review"],
                    complete=all(ids_by_dimension.values()),
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
