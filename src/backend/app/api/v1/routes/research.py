from fastapi import APIRouter

from app.agents.user_research import UserResearchArtifact
from app.api.dependencies import UserResearchServiceDependency

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
