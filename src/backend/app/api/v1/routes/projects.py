from typing import NoReturn

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import ProjectServiceDependency
from app.schemas.project import AgentRun, DecisionCreate, Project, ProjectCreate

router = APIRouter()


def not_implemented() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Contract scaffold only; business implementation is pending.",
    )


@router.post(
    "",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    summary="创建研究项目",
    description="保存结构化 Brief，并创建等待审批的真实项目、调研总管和首条事件。",
)
async def create_project(payload: ProjectCreate, service: ProjectServiceDependency) -> Project:
    return await service.create_project(payload)


@router.get(
    "",
    response_model=list[Project],
    summary="查询研究项目列表",
    description="按最近更新时间倒序返回研究项目。",
)
async def list_projects(service: ProjectServiceDependency) -> list[Project]:
    return await service.list_projects()


@router.get(
    "/{project_id}",
    response_model=Project,
    summary="查询研究项目详情",
)
async def get_project(project_id: str, service: ProjectServiceDependency) -> Project:
    return await service.get_project(project_id)


@router.get(
    "/{project_id}/agents",
    response_model=list[AgentRun],
    summary="查询 Agent 运行状态",
)
async def list_agent_runs(
    project_id: str,
    service: ProjectServiceDependency,
) -> list[AgentRun]:
    return await service.list_agent_runs(project_id)


@router.get("/{project_id}/events", response_model=None)
async def stream_project_events(project_id: str) -> None:
    del project_id
    not_implemented()


@router.post(
    "/{project_id}/decisions",
    response_model=Project,
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交人工审批决定",
    description="校验审批编号和状态迁移，记录决定并推进或终止项目。",
)
async def submit_decision(
    project_id: str,
    payload: DecisionCreate,
    service: ProjectServiceDependency,
) -> Project:
    return await service.submit_decision(project_id, payload)
