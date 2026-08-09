"""Source Fragment 到 Evidence Lake 的批次审核 API。"""

from fastapi import APIRouter, status

from app.api.dependencies import FragmentEvidencePipelineServiceDependency
from app.schemas.fragment_evidence import (
    FragmentEvidenceBatch,
    FragmentEvidenceBatchCreate,
    FragmentEvidenceBatchPage,
    FragmentEvidenceDecisionCreate,
    FragmentEvidenceDecisionResult,
)

router = APIRouter()


@router.get(
    "/{project_id}/fragment-evidence-batches",
    response_model=FragmentEvidenceBatchPage,
)
async def list_fragment_evidence_batches(
    project_id: str,
    service: FragmentEvidencePipelineServiceDependency,
) -> FragmentEvidenceBatchPage:
    return await service.list_batches(project_id)


@router.post(
    "/{project_id}/fragment-evidence-batches",
    response_model=FragmentEvidenceBatch,
    status_code=status.HTTP_201_CREATED,
)
async def create_fragment_evidence_batch(
    project_id: str,
    payload: FragmentEvidenceBatchCreate,
    service: FragmentEvidencePipelineServiceDependency,
) -> FragmentEvidenceBatch:
    return await service.create(project_id, payload)


@router.get(
    "/{project_id}/fragment-evidence-batches/{fragment_evidence_batch_id}",
    response_model=FragmentEvidenceBatch,
)
async def get_fragment_evidence_batch(
    project_id: str,
    fragment_evidence_batch_id: str,
    service: FragmentEvidencePipelineServiceDependency,
) -> FragmentEvidenceBatch:
    return await service.get(project_id, fragment_evidence_batch_id)


@router.post(
    "/{project_id}/fragment-evidence-batches/{fragment_evidence_batch_id}/decision",
    response_model=FragmentEvidenceDecisionResult,
)
async def decide_fragment_evidence_batch(
    project_id: str,
    fragment_evidence_batch_id: str,
    payload: FragmentEvidenceDecisionCreate,
    service: FragmentEvidencePipelineServiceDependency,
) -> FragmentEvidenceDecisionResult:
    return await service.decide(project_id, fragment_evidence_batch_id, payload)
