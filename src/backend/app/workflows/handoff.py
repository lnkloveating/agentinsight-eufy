"""Deterministically bridge parallel research outputs into product discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.workflows.contracts import (
    CompetitorGapProjection,
    CompetitorResearchProjection,
    ResearchAgentType,
    ResearchArtifact,
    ResearchArtifactProjection,
    ResearchHandoff,
    ResearchHandoffStatus,
    ResearchTaskStatus,
)

ADVANCING_STATUSES = {
    ResearchTaskStatus.COMPLETED,
    ResearchTaskStatus.PARTIAL,
}
COMPETITOR_AUDIT_STATUSES = {"passed", "passed_with_gaps"}


class _CitedView(BaseModel):
    evidence_ids: list[str] = Field(default_factory=list)


class _UserResearchPayloadView(BaseModel):
    summary_evidence_ids: list[str]
    event_chains: list[_CitedView]
    pain_points: list[_CitedView]
    unmet_needs: list[_CitedView]
    sample_biases: list[_CitedView]
    research_gaps: list[dict[str, object]]
    evidence_coverage: dict[str, object]


class _ProductProfileView(BaseModel):
    scope_label: str
    strengths: list[_CitedView]
    weaknesses: list[_CitedView]
    tradeoffs: list[_CitedView]


class _OpportunitySignalView(_CitedView):
    signal_id: str


class _ResearchGapView(BaseModel):
    scope_label: str
    dimension: str
    question: str


class _CoverageRowView(BaseModel):
    scope_label: str
    official_product_evidence_ids: list[str]
    price_channel_evidence_ids: list[str]
    user_review_evidence_ids: list[str]


class _EvidenceAuditView(BaseModel):
    status: str
    specialist_output_count: int


class _CompetitorSynthesisPayloadView(BaseModel):
    schema_name: str
    synthesis_status: str
    summary_evidence_ids: list[str]
    specialist_outputs: list[dict[str, object]]
    product_profiles: list[_ProductProfileView]
    comparative_insights: list[_CitedView]
    opportunity_signals: list[_OpportunitySignalView]
    research_gaps: list[_ResearchGapView]
    coverage_matrix: list[_CoverageRowView]
    evidence_audit: _EvidenceAuditView


def build_research_handoff(
    artifacts: dict[str, ResearchArtifact],
) -> ResearchHandoff:
    user = artifacts.get(ResearchAgentType.USER_RESEARCH.value)
    competitor = artifacts.get(ResearchAgentType.COMPETITOR_RESEARCH.value)
    issues: list[str] = []

    _validate_common(user, ResearchAgentType.USER_RESEARCH, issues)
    _validate_common(competitor, ResearchAgentType.COMPETITOR_RESEARCH, issues)

    if user is not None and user.status in ADVANCING_STATUSES and user.evidence_ids:
        try:
            typed_user = _UserResearchPayloadView.model_validate(user.payload)
        except ValidationError:
            issues.append("invalid_user_research_artifact")
        else:
            unsupported = sorted(
                _user_payload_evidence(typed_user) - set(user.evidence_ids)
            )
            if unsupported:
                issues.append("user_research_payload_evidence_outside_artifact")

    competitor_payload: _CompetitorSynthesisPayloadView | None = None
    if (
        competitor is not None
        and competitor.status in ADVANCING_STATUSES
        and competitor.evidence_ids
    ):
        try:
            competitor_payload = _CompetitorSynthesisPayloadView.model_validate(
                competitor.payload
            )
        except ValidationError:
            issues.append("invalid_competitor_synthesis_artifact")
        else:
            if competitor_payload.schema_name != "competitor_synthesis_intelligence":
                issues.append("invalid_competitor_synthesis_schema")
            if competitor_payload.evidence_audit.status not in COMPETITOR_AUDIT_STATUSES:
                issues.append(
                    "competitor_evidence_audit_not_passed:"
                    f"{competitor_payload.evidence_audit.status}"
                )
            if not competitor_payload.product_profiles:
                issues.append("competitor_synthesis_has_no_product_profiles")
            if (
                len(competitor_payload.specialist_outputs) != 3
                or competitor_payload.evidence_audit.specialist_output_count != 3
            ):
                issues.append("competitor_specialist_outputs_incomplete")
            if competitor_payload.synthesis_status not in {"completed", "partial"}:
                issues.append(
                    "competitor_synthesis_status_invalid:"
                    f"{competitor_payload.synthesis_status}"
                )
            if (
                competitor.status is ResearchTaskStatus.COMPLETED
                and competitor_payload.synthesis_status != "completed"
            ):
                issues.append("competitor_status_mismatch")
            profile_scope = {
                profile.scope_label for profile in competitor_payload.product_profiles
            }
            coverage_scope = {
                row.scope_label for row in competitor_payload.coverage_matrix
            }
            if profile_scope != coverage_scope:
                issues.append("competitor_coverage_scope_mismatch")
            unsupported = sorted(
                _competitor_payload_evidence(competitor_payload)
                - set(competitor.evidence_ids)
            )
            if unsupported:
                issues.append("competitor_payload_evidence_outside_artifact")

    blocking_issues = list(dict.fromkeys(issues))
    if blocking_issues:
        return ResearchHandoff(
            status=ResearchHandoffStatus.BLOCKED,
            ready_for_product_technical=False,
            user_research=_project(user),
            competitor_research=_project(competitor),
            merged_evidence_ids=_merged_evidence(user, competitor),
            issues=blocking_issues,
        )

    assert user is not None
    assert competitor is not None
    assert competitor_payload is not None
    competitor_projection = _competitor_projection(competitor_payload)
    has_gaps = (
        user.status is ResearchTaskStatus.PARTIAL
        or competitor.status is ResearchTaskStatus.PARTIAL
        or competitor_payload.synthesis_status == "partial"
        or competitor_payload.evidence_audit.status == "passed_with_gaps"
        or bool(competitor_projection.gaps)
        or bool(user.unknowns)
        or bool(competitor.unknowns)
    )
    return ResearchHandoff(
        status=(
            ResearchHandoffStatus.READY_WITH_GAPS
            if has_gaps
            else ResearchHandoffStatus.READY
        ),
        ready_for_product_technical=True,
        user_research=_project(user),
        competitor_research=_project(competitor),
        competitor_projection=competitor_projection,
        merged_evidence_ids=_merged_evidence(user, competitor),
        issues=[],
    )


def affected_research_agents(handoff: ResearchHandoff) -> set[ResearchAgentType]:
    affected: set[ResearchAgentType] = set()
    for issue in handoff.issues:
        if "user_research" in issue:
            affected.add(ResearchAgentType.USER_RESEARCH)
        if "competitor" in issue:
            affected.add(ResearchAgentType.COMPETITOR_RESEARCH)
    if handoff.user_research is None:
        affected.add(ResearchAgentType.USER_RESEARCH)
    if handoff.competitor_research is None:
        affected.add(ResearchAgentType.COMPETITOR_RESEARCH)
    return affected


def _validate_common(
    artifact: ResearchArtifact | None,
    agent_type: ResearchAgentType,
    issues: list[str],
) -> None:
    if artifact is None:
        issues.append(f"missing_artifact:{agent_type.value}")
        return
    if artifact.artifact_type != agent_type:
        issues.append(f"artifact_type_mismatch:{agent_type.value}")
    if artifact.status not in ADVANCING_STATUSES:
        issues.append(f"artifact_not_advancing:{agent_type.value}:{artifact.status.value}")
    if not artifact.evidence_ids:
        issues.append(f"artifact_has_no_evidence:{agent_type.value}")
    if artifact.errors:
        issues.append(f"artifact_has_errors:{agent_type.value}")


def _project(artifact: ResearchArtifact | None) -> ResearchArtifactProjection | None:
    if artifact is None:
        return None
    try:
        artifact_type = ResearchAgentType(artifact.artifact_type)
    except ValueError:
        return None
    return ResearchArtifactProjection(
        artifact_id=artifact.artifact_id,
        task_id=artifact.task_id,
        artifact_type=artifact_type,
        status=artifact.status,
        evidence_ids=artifact.evidence_ids,
        unknowns=artifact.unknowns,
        quality_score=artifact.quality_score,
    )


def _competitor_projection(
    payload: _CompetitorSynthesisPayloadView,
) -> CompetitorResearchProjection:
    gaps_by_scope: dict[str, CompetitorGapProjection] = {}
    for row in payload.coverage_matrix:
        missing: list[str] = []
        if not row.official_product_evidence_ids:
            missing.append("official_product")
        if not row.price_channel_evidence_ids:
            missing.append("price_channel")
        if not row.user_review_evidence_ids:
            missing.append("user_review")
        if missing:
            gaps_by_scope[row.scope_label] = CompetitorGapProjection(
                scope_label=row.scope_label,
                missing_dimensions=missing,
            )
    for gap in payload.research_gaps:
        projected = gaps_by_scope.setdefault(
            gap.scope_label,
            CompetitorGapProjection(scope_label=gap.scope_label),
        )
        if gap.dimension not in projected.missing_dimensions:
            projected.missing_dimensions.append(gap.dimension)
        projected.research_questions.append(gap.question)
    return CompetitorResearchProjection(
        schema_name=payload.schema_name,
        synthesis_status=payload.synthesis_status,
        evidence_audit_status=payload.evidence_audit.status,
        product_scope=[profile.scope_label for profile in payload.product_profiles],
        opportunity_signal_ids=[
            signal.signal_id for signal in payload.opportunity_signals
        ],
        gaps=list(gaps_by_scope.values()),
    )


def _merged_evidence(
    user: ResearchArtifact | None,
    competitor: ResearchArtifact | None,
) -> list[str]:
    return sorted(
        {
            evidence_id
            for artifact in (user, competitor)
            if artifact is not None
            for evidence_id in artifact.evidence_ids
        }
    )


def _user_payload_evidence(payload: _UserResearchPayloadView) -> set[str]:
    citations = set(payload.summary_evidence_ids)
    for collection in (
        payload.event_chains,
        payload.pain_points,
        payload.unmet_needs,
        payload.sample_biases,
    ):
        for item in collection:
            citations.update(item.evidence_ids)
    return citations


def _competitor_payload_evidence(
    payload: _CompetitorSynthesisPayloadView,
) -> set[str]:
    citations = set(payload.summary_evidence_ids)
    for profile in payload.product_profiles:
        for point in [*profile.strengths, *profile.weaknesses, *profile.tradeoffs]:
            citations.update(point.evidence_ids)
    for item in [*payload.comparative_insights, *payload.opportunity_signals]:
        citations.update(item.evidence_ids)
    for row in payload.coverage_matrix:
        citations.update(row.official_product_evidence_ids)
        citations.update(row.price_channel_evidence_ids)
        citations.update(row.user_review_evidence_ids)
    return citations
