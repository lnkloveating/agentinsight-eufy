"""已确认竞品候选来源的批量接入 API。"""

from fastapi import APIRouter, Response, status

from app.api.dependencies import CompetitorSourceOnboardingServiceDependency
from app.schemas.competitor_source_onboarding import (
    CompetitorSourceOnboardingCreate,
    CompetitorSourceOnboardingPage,
    CompetitorSourceOnboardingResult,
)

router = APIRouter()


@router.get(
    "/{project_id}/competitor-source-onboardings",
    response_model=CompetitorSourceOnboardingPage,
)
async def list_competitor_source_onboardings(
    project_id: str,
    service: CompetitorSourceOnboardingServiceDependency,
) -> CompetitorSourceOnboardingPage:
    return await service.list_onboardings(project_id)


@router.post(
    "/{project_id}/competitor-source-onboardings",
    response_model=CompetitorSourceOnboardingResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_competitor_source_onboarding(
    project_id: str,
    payload: CompetitorSourceOnboardingCreate,
    response: Response,
    service: CompetitorSourceOnboardingServiceDependency,
) -> CompetitorSourceOnboardingResult:
    result = await service.create(project_id, payload)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result
