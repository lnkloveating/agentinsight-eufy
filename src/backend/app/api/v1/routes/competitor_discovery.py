"""竞品候选发现 Agent 与 Candidate Gate API。"""

from fastapi import APIRouter

from app.agents.competitor import (
    CompetitorCandidateDecisionCreate,
    CompetitorCandidateDecisionResult,
    CompetitorDiscoveryArtifact,
    CompetitorDiscoveryRunCreate,
)
from app.api.dependencies import CompetitorDiscoveryServiceDependency

router = APIRouter()


@router.post(
    "/{project_id}/agents/competitor-discovery",
    response_model=CompetitorDiscoveryArtifact,
)
async def run_competitor_discovery(
    project_id: str,
    payload: CompetitorDiscoveryRunCreate,
    service: CompetitorDiscoveryServiceDependency,
) -> CompetitorDiscoveryArtifact:
    return await service.run(project_id, payload)


@router.get(
    "/{project_id}/agents/competitor-discovery/artifacts",
    response_model=list[CompetitorDiscoveryArtifact],
)
async def list_competitor_discovery_artifacts(
    project_id: str,
    service: CompetitorDiscoveryServiceDependency,
) -> list[CompetitorDiscoveryArtifact]:
    return await service.list_artifacts(project_id)


@router.post(
    "/{project_id}/agents/competitor-discovery/artifacts/{artifact_id}/decision",
    response_model=CompetitorCandidateDecisionResult,
)
async def decide_competitor_candidates(
    project_id: str,
    artifact_id: str,
    payload: CompetitorCandidateDecisionCreate,
    service: CompetitorDiscoveryServiceDependency,
) -> CompetitorCandidateDecisionResult:
    return await service.decide(project_id, artifact_id, payload)
