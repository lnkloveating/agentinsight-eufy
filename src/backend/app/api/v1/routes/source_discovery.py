"""项目级公开来源搜索发现接口。"""

from fastapi import APIRouter, Query, status

from app.api.dependencies import SearchDiscoveryServiceDependency
from app.schemas.search_discovery import (
    SearchDiscoveryCreate,
    SearchDiscoveryRun,
    SearchDiscoveryRunPage,
)

router = APIRouter()


@router.get(
    "/{project_id}/source-discovery/searches",
    response_model=SearchDiscoveryRunPage,
)
async def list_search_discovery_runs(
    project_id: str,
    service: SearchDiscoveryServiceDependency,
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchDiscoveryRunPage:
    return await service.list_runs(project_id, limit=limit)


@router.post(
    "/{project_id}/source-discovery/searches",
    response_model=SearchDiscoveryRun,
    status_code=status.HTTP_201_CREATED,
)
async def create_search_discovery_run(
    project_id: str,
    payload: SearchDiscoveryCreate,
    service: SearchDiscoveryServiceDependency,
) -> SearchDiscoveryRun:
    return await service.create(project_id, payload)


@router.get(
    "/{project_id}/source-discovery/searches/{search_discovery_run_id}",
    response_model=SearchDiscoveryRun,
)
async def get_search_discovery_run(
    project_id: str,
    search_discovery_run_id: str,
    service: SearchDiscoveryServiceDependency,
) -> SearchDiscoveryRun:
    return await service.get(project_id, search_discovery_run_id)
