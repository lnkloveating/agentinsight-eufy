"""竞品研究资料发现与人工确认 API。"""

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.api.dependencies import (
    CompetitorMaterialDiscoveryServiceDependency,
    CompetitorSourceProcessingDispatcherDependency,
)
from app.schemas.competitor_material_discovery import (
    CompetitorMaterialDecisionCreate,
    CompetitorMaterialDecisionResult,
    CompetitorMaterialDiscovery,
    CompetitorMaterialDiscoveryCreate,
    CompetitorMaterialDiscoveryPage,
)

router = APIRouter()


@router.get(
    "/{project_id}/competitor-material-discoveries",
    response_model=CompetitorMaterialDiscoveryPage,
)
async def list_competitor_material_discoveries(
    project_id: str,
    service: CompetitorMaterialDiscoveryServiceDependency,
) -> CompetitorMaterialDiscoveryPage:
    return await service.list_discoveries(project_id)


@router.post(
    "/{project_id}/competitor-material-discoveries",
    response_model=CompetitorMaterialDiscovery,
    status_code=status.HTTP_201_CREATED,
)
async def create_competitor_material_discovery(
    project_id: str,
    payload: CompetitorMaterialDiscoveryCreate,
    service: CompetitorMaterialDiscoveryServiceDependency,
) -> CompetitorMaterialDiscovery:
    return await service.create(project_id, payload)


@router.get(
    "/{project_id}/competitor-material-discoveries/{material_discovery_id}",
    response_model=CompetitorMaterialDiscovery,
)
async def get_competitor_material_discovery(
    project_id: str,
    material_discovery_id: str,
    service: CompetitorMaterialDiscoveryServiceDependency,
) -> CompetitorMaterialDiscovery:
    return await service.get(project_id, material_discovery_id)


@router.post(
    "/{project_id}/competitor-material-discoveries/{material_discovery_id}/decision",
    response_model=CompetitorMaterialDecisionResult,
    status_code=status.HTTP_201_CREATED,
)
async def decide_competitor_material_discovery(
    project_id: str,
    material_discovery_id: str,
    payload: CompetitorMaterialDecisionCreate,
    background_tasks: BackgroundTasks,
    response: Response,
    service: CompetitorMaterialDiscoveryServiceDependency,
    dispatcher: CompetitorSourceProcessingDispatcherDependency,
) -> CompetitorMaterialDecisionResult:
    result = await service.decide(project_id, material_discovery_id, payload)
    source_asset_ids = [
        item.source_asset.source_asset_id for item in result.decision.selections
    ]
    if source_asset_ids:
        background_tasks.add_task(
            dispatcher.dispatch,
            project_id,
            material_discovery_id,
            source_asset_ids,
            batch_type="competitor_material_discovery",
        )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result
