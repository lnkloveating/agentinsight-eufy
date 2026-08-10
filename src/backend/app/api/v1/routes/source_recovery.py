"""资料恢复任务、用户补充和人工带缺口继续接口。"""

from fastapi import APIRouter, status

from app.api.dependencies import SourceRecoveryServiceDependency
from app.schemas.source_recovery import (
    SourceRecovery,
    SourceRecoveryCreate,
    SourceRecoveryDecisionCreate,
    SourceRecoveryEvidenceSubmissionCreate,
    SourceRecoveryPage,
    SourceRecoverySubmissionCreate,
)

router = APIRouter()


@router.get(
    "/{project_id}/source-recoveries",
    response_model=SourceRecoveryPage,
)
async def list_source_recoveries(
    project_id: str,
    service: SourceRecoveryServiceDependency,
) -> SourceRecoveryPage:
    return await service.list_recoveries(project_id)


@router.post(
    "/{project_id}/source-recoveries",
    response_model=SourceRecovery,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_recovery(
    project_id: str,
    payload: SourceRecoveryCreate,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.create(project_id, payload)


@router.get(
    "/{project_id}/source-recoveries/{source_recovery_id}",
    response_model=SourceRecovery,
)
async def get_source_recovery(
    project_id: str,
    source_recovery_id: str,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.get(project_id, source_recovery_id)


@router.post(
    "/{project_id}/source-recoveries/{source_recovery_id}/submissions",
    response_model=SourceRecovery,
    status_code=status.HTTP_201_CREATED,
)
async def submit_source_recovery(
    project_id: str,
    source_recovery_id: str,
    payload: SourceRecoverySubmissionCreate,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.submit(project_id, source_recovery_id, payload)


@router.post(
    "/{project_id}/source-recoveries/{source_recovery_id}/evidence-submissions",
    response_model=SourceRecovery,
    status_code=status.HTTP_201_CREATED,
)
async def submit_source_recovery_evidence(
    project_id: str,
    source_recovery_id: str,
    payload: SourceRecoveryEvidenceSubmissionCreate,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.submit_evidence(project_id, source_recovery_id, payload)


@router.post(
    "/{project_id}/source-recoveries/{source_recovery_id}/decisions",
    response_model=SourceRecovery,
)
async def decide_source_recovery(
    project_id: str,
    source_recovery_id: str,
    payload: SourceRecoveryDecisionCreate,
    service: SourceRecoveryServiceDependency,
) -> SourceRecovery:
    return await service.decide(project_id, source_recovery_id, payload)
