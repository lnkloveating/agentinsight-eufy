import asyncio

from fastapi import APIRouter, Request, status

from app.agents.product_technical import ProductTechnicalArtifact
from app.agents.user_research import UserResearchArtifact
from app.api.dependencies import (
    ProductTechnicalServiceDependency,
    SourceRecoveryServiceDependency,
    UserResearchServiceDependency,
)
from app.schemas.source_recovery import (
    AgentArtifactGapPage,
    AgentArtifactSourceRecoveryCreate,
    ProductTechnicalSourceRecoveryCreate,
    RecoverableAgentType,
    SourceRecovery,
)

router = APIRouter()


@router.post("/{project_id}/research/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_initial_research(project_id: str, request: Request) -> dict[str, str]:
    launcher = getattr(request.app.state, "research_launcher", None)
    if launcher is None:
        return {"project_id": project_id, "status": "unavailable"}
    asyncio.create_task(launcher(project_id), name=f"retry-initial-research-{project_id}")
    return {"project_id": project_id, "status": "started"}


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


@router.post(
    "/{project_id}/agents/product-technical/artifacts/{artifact_id}/source-recovery",
    response_model=SourceRecovery,
    status_code=status.HTTP_201_CREATED,
    summary="把产品技术缺口转换为用户补研任务",
)
async def create_product_technical_source_recovery(
    project_id: str,
    artifact_id: str,
    payload: ProductTechnicalSourceRecoveryCreate,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.create_from_product_technical(project_id, artifact_id, payload)


@router.get(
    "/{project_id}/agents/{agent_type}/artifacts/{artifact_id}/gaps",
    response_model=AgentArtifactGapPage,
    summary="查询任意领域 Agent Artifact 的统一补研缺口",
)
async def list_agent_artifact_gaps(
    project_id: str,
    agent_type: RecoverableAgentType,
    artifact_id: str,
    service: SourceRecoveryServiceDependency,
) -> AgentArtifactGapPage:
    return await service.list_agent_artifact_gaps(project_id, agent_type, artifact_id)


@router.post(
    "/{project_id}/agents/{agent_type}/artifacts/{artifact_id}/source-recovery",
    response_model=SourceRecovery,
    status_code=status.HTTP_201_CREATED,
    summary="把任意领域 Agent 缺口转换为统一补研任务",
)
async def create_agent_artifact_source_recovery(
    project_id: str,
    agent_type: RecoverableAgentType,
    artifact_id: str,
    payload: AgentArtifactSourceRecoveryCreate,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.create_from_agent_artifact(project_id, agent_type, artifact_id, payload)
