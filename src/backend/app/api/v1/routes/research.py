from fastapi import APIRouter, status

from app.agents.competitor import CompetitorEcosystemArtifact
from app.agents.ecosystem_opportunity import EcosystemOpportunityArtifact
from app.agents.security_policy import SecurityPolicyArtifact, SecurityPolicyRunCreate
from app.agents.technical_feasibility import (
    TechnicalFeasibilityArtifact,
    TechnicalFeasibilityRunCreate,
)
from app.agents.user_research import UserResearchArtifact
from app.api.dependencies import (
    CompetitorEcosystemServiceDependency,
    EcosystemOpportunityServiceDependency,
    SecurityPolicyServiceDependency,
    SourceRecoveryServiceDependency,
    TechnicalFeasibilityServiceDependency,
    UserResearchServiceDependency,
)
from app.schemas.source_recovery import (
    AgentArtifactGapPage,
    AgentArtifactSourceRecoveryCreate,
    RecoverableAgentType,
    SourceRecovery,
)

router = APIRouter()


@router.post(
    "/{project_id}/agents/security-policy-compiler",
    response_model=SecurityPolicyArtifact,
    summary="编译 dry-run 家庭安防策略",
)
async def run_security_policy_compiler(
    project_id: str,
    payload: SecurityPolicyRunCreate,
    service: SecurityPolicyServiceDependency,
) -> SecurityPolicyArtifact:
    return await service.run(project_id, payload)


@router.get(
    "/{project_id}/agents/security-policy-compiler/artifacts",
    response_model=list[SecurityPolicyArtifact],
    summary="查询安全策略 Artifact 历史版本",
)
async def list_security_policy_artifacts(
    project_id: str,
    service: SecurityPolicyServiceDependency,
) -> list[SecurityPolicyArtifact]:
    return await service.list_artifacts(project_id)


@router.post(
    "/{project_id}/agents/competitor-ecosystem",
    response_model=CompetitorEcosystemArtifact,
    summary="运行竞品生态分析 Agent",
    description=(
        "复用候选发现和三个 A2A 事实专家，生成经过 Evidence 审计的竞品生态能力矩阵。"
        "资料未覆盖时保持 unknown，不改写为竞品没有。"
    ),
)
async def run_competitor_ecosystem(
    project_id: str,
    service: CompetitorEcosystemServiceDependency,
) -> CompetitorEcosystemArtifact:
    return await service.run(project_id)


@router.get(
    "/{project_id}/agents/competitor-ecosystem/artifacts",
    response_model=list[CompetitorEcosystemArtifact],
    summary="查询竞品生态分析 Artifact 历史版本",
)
async def list_competitor_ecosystem_artifacts(
    project_id: str,
    service: CompetitorEcosystemServiceDependency,
) -> list[CompetitorEcosystemArtifact]:
    return await service.list_artifacts(project_id)


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
    "/{project_id}/agents/ecosystem-opportunity",
    response_model=EcosystemOpportunityArtifact,
    summary="运行生态机会 Agent",
    description=(
        "读取最新用户研究、竞品生态 Artifact、共享 Evidence 和设备能力图，动态生成有证据边界的"
        "设备功能、设备产品或生态服务机会；未知设备能力保持为技术假设和补研缺口。"
    ),
)
async def run_ecosystem_opportunity(
    project_id: str,
    service: EcosystemOpportunityServiceDependency,
) -> EcosystemOpportunityArtifact:
    return await service.run(project_id)


@router.get(
    "/{project_id}/agents/ecosystem-opportunity/artifacts",
    response_model=list[EcosystemOpportunityArtifact],
    summary="查询生态机会 Artifact 历史版本",
)
async def list_ecosystem_opportunity_artifacts(
    project_id: str,
    service: EcosystemOpportunityServiceDependency,
) -> list[EcosystemOpportunityArtifact]:
    return await service.list_artifacts(project_id)


@router.post(
    "/{project_id}/agents/technical-feasibility",
    response_model=TechnicalFeasibilityArtifact,
    summary="运行技术可行性 Agent",
    description=(
        "只评估 AI Native Ecosystem Gate 已选择的机会；模型提出技术需求，后端结合"
        " Evidence 与 Device Capability Graph 确定可行性结论和补研缺口。"
    ),
)
async def run_technical_feasibility(
    project_id: str,
    payload: TechnicalFeasibilityRunCreate,
    service: TechnicalFeasibilityServiceDependency,
) -> TechnicalFeasibilityArtifact:
    return await service.run(project_id, payload)


@router.get(
    "/{project_id}/agents/technical-feasibility/artifacts",
    response_model=list[TechnicalFeasibilityArtifact],
    summary="查询技术可行性 Artifact 历史版本",
)
async def list_technical_feasibility_artifacts(
    project_id: str,
    service: TechnicalFeasibilityServiceDependency,
) -> list[TechnicalFeasibilityArtifact]:
    return await service.list_artifacts(project_id)


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
