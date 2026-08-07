from fastapi import APIRouter

from app.api.dependencies import ExternalRuntimeCatalogDependency
from app.schemas.runtime import ExternalRuntimePage

router = APIRouter()


@router.get(
    "",
    response_model=ExternalRuntimePage,
    summary="查询可选择的外部 Agent Runtime",
    description="只返回经过探测的能力和可用状态，不暴露凭据名称或本机路径。",
)
async def list_external_runtimes(
    catalog: ExternalRuntimeCatalogDependency,
) -> ExternalRuntimePage:
    return await catalog.public_page()
