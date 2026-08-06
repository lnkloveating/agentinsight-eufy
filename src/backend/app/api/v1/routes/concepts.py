from fastapi import APIRouter

from app.api.dependencies import InnovationServiceDependency
from app.api.v1.routes.projects import not_implemented
from app.schemas.concept import Concept
from app.schemas.innovation import Innovation

router = APIRouter()


@router.get("/{project_id}/concepts", response_model=list[Concept])
async def list_concepts(project_id: str) -> list[Concept]:
    del project_id
    not_implemented()


@router.get("/{project_id}/innovations", response_model=list[Innovation])
async def list_innovations(
    project_id: str, service: InnovationServiceDependency
) -> list[Innovation]:
    return await service.list_innovations(project_id)
