import asyncio

from fastapi import APIRouter, Request, status

from app.agents.competitor import CompetitorEcosystemArtifact
from app.agents.ecosystem_opportunity import EcosystemOpportunityArtifact
from app.agents.product_technical import ProductTechnicalArtifact
from app.agents.user_research import UserResearchArtifact
from app.api.dependencies import (
    CompetitorEcosystemServiceDependency,
    EcosystemOpportunityServiceDependency,
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
    "/{project_id}/agents/competitor-ecosystem",
    response_model=CompetitorEcosystemArtifact,
    summary="杩愯绔炲搧鐢熸€佸垎鏋?Agent",
    description=(
        "澶嶇敤鍊欓€夊彂鐜板拰涓変釜 A2A 浜嬪疄涓撳锛岀敓鎴愬甫 Evidence 瀹¤鐨勭珵鍝佺敓鎬佽兘鍔涚煩闃点€?
        "璧勬枡鏈鐩栨椂淇濇寔 unknown锛屼笉鏀瑰啓涓虹珵鍝佹病鏈夈€?
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
    summary="鏌ヨ绔炲搧鐢熸€佸垎鏋?Artifact 鍘嗗彶鐗堟湰",
)
async def list_competitor_ecosystem_artifacts(
    project_id: str,
    service: CompetitorEcosystemServiceDependency,
) -> list[CompetitorEcosystemArtifact]:
    return await service.list_artifacts(project_id)



@router.post(
    "/{project_id}/agents/user-research",
    response_model=UserResearchArtifact,
    summary="杩愯鐢ㄦ埛鐮旂┒ Agent",
    description=(
        "浠?Evidence Lake 鏋勫缓鍙楁帶涓婁笅鏂囷紝閫氳繃宸叉敞鍐?Runtime 璋冪敤鐪熷疄妯″瀷骞朵繚瀛?Artifact銆?
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
    summary="鏌ヨ鐢ㄦ埛鐮旂┒ Artifact 鍘嗗彶鐗堟湰",
)
async def list_user_research_artifacts(
    project_id: str,
    service: UserResearchServiceDependency,
) -> list[UserResearchArtifact]:
    return await service.list_artifacts(project_id)


@router.post(
    "/{project_id}/agents/ecosystem-opportunity",
    response_model=EcosystemOpportunityArtifact,
    summary="杩愯鐢熸€佹満浼?Agent",
    description=(
        "璇诲彇鏈€鏂扮敤鎴风爺绌躲€佺珵鍝佺敓鎬?Artifact銆佸叡浜?Evidence 鍜岃澶囪兘鍔涘浘锛屽姩鎬佺敓鎴愭湁璇佹嵁杈圭晫鐨?
        "璁惧鍔熻兘銆佽澶囦骇鍝佹垨鐢熸€佹湇鍔℃満浼氾紱鏈煡璁惧鑳藉姏淇濇寔涓烘妧鏈亣璁惧拰琛ョ爺缂哄彛銆?
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
    summary="鏌ヨ鐢熸€佹満浼?Artifact 鍘嗗彶鐗堟湰",
)
async def list_ecosystem_opportunity_artifacts(
    project_id: str,
    service: EcosystemOpportunityServiceDependency,
) -> list[EcosystemOpportunityArtifact]:
    return await service.list_artifacts(project_id)


@router.post(
    "/{project_id}/agents/product-technical",
    response_model=ProductTechnicalArtifact,
    summary="杩愯浜у搧鎶€鏈満浼?Agent",
    description=(
        "璇诲彇鏈€鏂扮敤鎴风爺绌朵笌绔炲搧缁煎悎 Artifact锛屽姩鎬佺敓鎴愭湁 Evidence 寮曠敤鐨勬湭鏉ヤ骇鍝佸€欓€夛紝"
        "骞剁敱鍚庣鎵ц Event Understanding Gate銆?
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
    summary="鏌ヨ浜у搧鎶€鏈満浼?Artifact 鍘嗗彶鐗堟湰",
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
    summary="鎶婁骇鍝佹妧鏈己鍙ｈ浆鎹负鐢ㄦ埛琛ョ爺浠诲姟",
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
    summary="鏌ヨ浠绘剰棰嗗煙 Agent Artifact 鐨勭粺涓€琛ョ爺缂哄彛",
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
    summary="鎶婁换鎰忛鍩?Agent 缂哄彛杞崲涓虹粺涓€琛ョ爺浠诲姟",
)
async def create_agent_artifact_source_recovery(
    project_id: str,
    agent_type: RecoverableAgentType,
    artifact_id: str,
    payload: AgentArtifactSourceRecoveryCreate,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.create_from_agent_artifact(project_id, agent_type, artifact_id, payload)
