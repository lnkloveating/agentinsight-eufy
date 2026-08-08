"""项目级资料范围与准备度接口。"""

from fastapi import APIRouter

from app.api.dependencies import SourceRequirementServiceDependency
from app.schemas.source_requirements import (
    SourceRequirementAssessment,
    SourceRequirementScopeUpdate,
)

router = APIRouter()


@router.get(
    "/{project_id}/source-requirements",
    response_model=SourceRequirementAssessment,
)
async def get_source_requirements(
    project_id: str,
    service: SourceRequirementServiceDependency,
) -> SourceRequirementAssessment:
    return await service.get(project_id)


@router.put(
    "/{project_id}/source-requirements/scope",
    response_model=SourceRequirementAssessment,
)
async def update_source_requirement_scope(
    project_id: str,
    payload: SourceRequirementScopeUpdate,
    service: SourceRequirementServiceDependency,
) -> SourceRequirementAssessment:
    return await service.update_scope(project_id, payload)
