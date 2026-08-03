from fastapi import APIRouter

from app.api.v1.routes.projects import not_implemented
from app.schemas.concept import Concept

router = APIRouter()


@router.get("/{project_id}/concepts", response_model=list[Concept])
async def list_concepts(project_id: str) -> list[Concept]:
    del project_id
    not_implemented()
