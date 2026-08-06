"""前端模型选择器使用的安全模型目录。"""

from fastapi import APIRouter

from app.api.dependencies import ModelCatalogDependency, ModelCredentialDependency
from app.schemas.model import ModelPage

router = APIRouter()


@router.get(
    "",
    response_model=ModelPage,
    summary="查询可选择模型",
    description="返回已启用模型及凭据可用状态，不暴露 API Key 或环境变量名。",
)
async def list_models(
    catalog: ModelCatalogDependency,
    credentials: ModelCredentialDependency,
) -> ModelPage:
    return catalog.public_page(credentials)
