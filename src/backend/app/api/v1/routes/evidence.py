from fastapi import APIRouter

from app.api.v1.routes.projects import not_implemented
from app.schemas.evidence import Claim, EvidencePage

router = APIRouter()


@router.get("/{project_id}/evidence", response_model=EvidencePage)
async def list_evidence(project_id: str, cursor: str | None = None) -> EvidencePage:
    del project_id, cursor
    not_implemented()


@router.get("/{project_id}/claims", response_model=list[Claim])
async def list_claims(project_id: str) -> list[Claim]:
    del project_id
    not_implemented()
