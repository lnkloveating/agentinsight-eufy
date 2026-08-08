from fastapi import APIRouter

from app.api.dependencies import EvidenceQueryServiceDependency
from app.schemas.evidence import Claim, EvidencePage, EvidenceStatus

router = APIRouter()


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


@router.get("/{project_id}/claims", response_model=list[Claim])
async def list_claims(project_id: str, service: EvidenceQueryServiceDependency) -> list[Claim]:
    return await service.list_claims(project_id)
