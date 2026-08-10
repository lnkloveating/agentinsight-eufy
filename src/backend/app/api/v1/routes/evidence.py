from fastapi import APIRouter

from app.api.dependencies import (
    EvidenceServiceDependency,
    EvidenceQueryServiceDependency,
    EvidenceRetrievalServiceDependency,
)
from app.schemas.evidence import Claim, EvidenceIngest, EvidenceIngestResult, EvidencePage, EvidenceStatus
from app.schemas.evidence_retrieval import EvidenceRetrievalQuery, EvidenceRetrievalResult

router = APIRouter()


@router.post("/{project_id}/evidence", response_model=EvidenceIngestResult, status_code=201)
async def ingest_evidence(
    project_id: str,
    payload: EvidenceIngest,
    service: EvidenceServiceDependency,
) -> EvidenceIngestResult:
    return await service.ingest(project_id, payload)


@router.get("/{project_id}/evidence", response_model=EvidencePage)
async def list_evidence(
    project_id: str,
    service: EvidenceQueryServiceDependency,
    cursor: str | None = None,
    status: EvidenceStatus | None = None,
    source_type: str | None = None,
) -> EvidencePage:
    return await service.list_evidence(
        project_id,
        cursor=cursor,
        status=status,
        source_type=source_type,
    )


@router.post(
    "/{project_id}/evidence/retrievals",
    response_model=EvidenceRetrievalResult,
    summary="检索项目共享 Evidence 上下文",
)
async def retrieve_evidence(
    project_id: str,
    payload: EvidenceRetrievalQuery,
    service: EvidenceRetrievalServiceDependency,
) -> EvidenceRetrievalResult:
    return await service.retrieve(project_id, payload)


@router.get("/{project_id}/claims", response_model=list[Claim])
async def list_claims(project_id: str, service: EvidenceQueryServiceDependency) -> list[Claim]:
    return await service.list_claims(project_id)
