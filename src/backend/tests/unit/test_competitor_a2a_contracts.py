import pytest
from pydantic import ValidationError

from app.integrations.a2a import (
    A2ASpecialistRegistry,
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    CompetitorSpecialistType,
    EvidenceRequest,
)
from app.workflows.contracts import ResearchTaskStatus


def _request() -> EvidenceRequest:
    return EvidenceRequest(
        request_id="request_official",
        project_id="project_contract",
        parent_task_id="task_competitor",
        specialist_type=CompetitorSpecialistType.OFFICIAL_PRODUCT,
        research_questions=["Which source-backed product capabilities are in scope?"],
        product_scope=["target product"],
        region="US",
        evidence_types=["official_product_page"],
        allowed_claim_types=["product_capability"],
    )


def test_evidence_request_rejects_duplicate_research_inputs() -> None:
    with pytest.raises(ValidationError, match="cannot contain duplicates"):
        _request().model_copy(
            update={"research_questions": ["same question", "same question"]}
        ).model_dump()
        EvidenceRequest.model_validate(
            {
                **_request().model_dump(),
                "research_questions": ["same question", "same question"],
            }
        )


def test_completed_specialist_artifact_requires_cited_findings() -> None:
    with pytest.raises(ValidationError, match="must contain findings"):
        CompetitorSpecialistArtifact(
            a2a_task_id="a2a_official",
            request_id="request_official",
            specialist_type=CompetitorSpecialistType.OFFICIAL_PRODUCT,
            status=ResearchTaskStatus.COMPLETED,
            quality_score=80,
        )


def test_specialist_finding_ids_must_be_declared_by_artifact() -> None:
    with pytest.raises(ValidationError, match="must be included"):
        CompetitorSpecialistArtifact(
            a2a_task_id="a2a_official",
            request_id="request_official",
            specialist_type=CompetitorSpecialistType.OFFICIAL_PRODUCT,
            status=ResearchTaskStatus.COMPLETED,
            findings=[
                CompetitorFinding(
                    finding_id="finding_1",
                    category="capability",
                    statement="A test-only factual statement.",
                    evidence_ids=["ev_declared_elsewhere"],
                    confidence=0.8,
                )
            ],
            evidence_ids=["ev_different"],
            quality_score=80,
        )


class _Adapter:
    adapter_type = "test-specialist"

    async def execute(self, invocation: object) -> object:
        return invocation


def test_specialist_registry_requires_explicit_non_duplicate_binding() -> None:
    registry = A2ASpecialistRegistry()
    adapter = _Adapter()
    registry.bind(CompetitorSpecialistType.OFFICIAL_PRODUCT, adapter)

    assert registry.resolve(CompetitorSpecialistType.OFFICIAL_PRODUCT) is not None
    assert registry.resolve(CompetitorSpecialistType.USER_REVIEW) is None
    with pytest.raises(ValueError, match="already bound"):
        registry.bind(CompetitorSpecialistType.OFFICIAL_PRODUCT, adapter)

