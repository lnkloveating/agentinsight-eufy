from fastapi import APIRouter

from app.agents.product_technical import ProductTechnicalArtifact
from app.agents.user_research import UserResearchArtifact
from app.api.dependencies import (
    ProductTechnicalServiceDependency,
    UserResearchServiceDependency,
)

router = APIRouter()


@router.post(
    "/{project_id}/agents/user-research",
    response_model=UserResearchArtifact,
    summary="运行用户研究 Agent",
    description=(
        "从 Evidence Lake 构建受控上下文，通过已注册 Runtime 调用真实模型并保存 Artifact。"
    ),
)
async def run_user_research(
    project_id: str,
    service: UserResearchServiceDependency,
) -> UserResearchArtifact:
    return await service.run(project_id)


@router.get(
    "/{project_id}/agents/user-research/artifacts",
    response_model=list[UserResearchArtifact],
    summary="查询用户研究 Artifact 历史版本",
)
async def list_user_research_artifacts(
    project_id: str,
    service: UserResearchServiceDependency,
) -> list[UserResearchArtifact]:
    return await service.list_artifacts(project_id)


@router.post(
    "/{project_id}/agents/product-technical",
    response_model=ProductTechnicalArtifact,
    summary="运行产品技术机会 Agent",
    description=(
        "读取最新用户研究与竞品综合 Artifact，动态生成有 Evidence 引用的未来产品候选，"
        "并由后端执行 Event Understanding Gate。"
    ),
)
async def run_product_technical(
    project_id: str,
    service: ProductTechnicalServiceDependency,
) -> ProductTechnicalArtifact:
    return await service.run(project_id)


@router.get(
    "/{project_id}/agents/product-technical/artifacts",
    response_model=list[ProductTechnicalArtifact],
    summary="查询产品技术机会 Artifact 历史版本",
)
async def list_product_technical_artifacts(
    project_id: str,
    service: ProductTechnicalServiceDependency,
) -> list[ProductTechnicalArtifact]:
    return await service.list_artifacts(project_id)
