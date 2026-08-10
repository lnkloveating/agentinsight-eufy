"""设备能力目录、家庭快照和能力覆盖查询 API。"""

from fastapi import APIRouter, Response, status

from app.api.dependencies import DeviceCapabilityServiceDependency
from app.schemas.device_capability import (
    CatalogDevice,
    CatalogDeviceCreate,
    CatalogDevicePage,
    DeviceCapabilityQuery,
    DeviceCapabilityQueryResult,
    HouseholdSnapshot,
    HouseholdSnapshotCreate,
)

router = APIRouter()


@router.post(
    "/{project_id}/device-capabilities/catalog",
    response_model=CatalogDevice,
    status_code=status.HTTP_201_CREATED,
    summary="登记带 Evidence 血缘的厂商设备能力记录",
)
async def create_catalog_device(
    project_id: str,
    payload: CatalogDeviceCreate,
    service: DeviceCapabilityServiceDependency,
) -> CatalogDevice:
    return await service.create_catalog_device(project_id, payload)


@router.get(
    "/{project_id}/device-capabilities/catalog",
    response_model=CatalogDevicePage,
    summary="查询项目设备能力目录",
)
async def list_catalog_devices(
    project_id: str,
    service: DeviceCapabilityServiceDependency,
) -> CatalogDevicePage:
    return await service.list_catalog_devices(project_id)


@router.get(
    "/{project_id}/device-capabilities/catalog/{catalog_device_id}",
    response_model=CatalogDevice,
    summary="查询单个厂商设备能力记录",
)
async def get_catalog_device(
    project_id: str,
    catalog_device_id: str,
    service: DeviceCapabilityServiceDependency,
) -> CatalogDevice:
    return await service.get_catalog_device(project_id, catalog_device_id)


@router.put(
    "/{project_id}/device-capabilities/catalog/{catalog_device_id}",
    response_model=CatalogDevice,
    summary="替换厂商设备能力记录",
)
async def replace_catalog_device(
    project_id: str,
    catalog_device_id: str,
    payload: CatalogDeviceCreate,
    service: DeviceCapabilityServiceDependency,
) -> CatalogDevice:
    return await service.replace_catalog_device(project_id, catalog_device_id, payload)


@router.delete(
    "/{project_id}/device-capabilities/catalog/{catalog_device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除未被家庭快照引用的厂商设备记录",
)
async def delete_catalog_device(
    project_id: str,
    catalog_device_id: str,
    service: DeviceCapabilityServiceDependency,
) -> Response:
    await service.delete_catalog_device(project_id, catalog_device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{project_id}/device-capabilities/household-snapshot",
    response_model=HouseholdSnapshot,
    summary="保存用户授权的家庭设备快照新版本",
)
async def replace_household_snapshot(
    project_id: str,
    payload: HouseholdSnapshotCreate,
    service: DeviceCapabilityServiceDependency,
) -> HouseholdSnapshot:
    return await service.replace_household_snapshot(project_id, payload)


@router.get(
    "/{project_id}/device-capabilities/household-snapshot",
    response_model=HouseholdSnapshot,
    summary="查询当前家庭设备快照",
)
async def get_household_snapshot(
    project_id: str,
    service: DeviceCapabilityServiceDependency,
) -> HouseholdSnapshot:
    return await service.get_household_snapshot(project_id)


@router.post(
    "/{project_id}/device-capabilities/queries",
    response_model=DeviceCapabilityQueryResult,
    summary="查询家庭现有设备能否支撑方案所需能力",
)
async def query_capabilities(
    project_id: str,
    payload: DeviceCapabilityQuery,
    service: DeviceCapabilityServiceDependency,
) -> DeviceCapabilityQueryResult:
    return await service.query_capabilities(project_id, payload)
