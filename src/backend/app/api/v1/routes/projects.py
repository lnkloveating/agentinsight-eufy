from collections.abc import AsyncIterator
from typing import NoReturn

from fastapi import APIRouter, Header, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import EventServiceDependency, ProjectServiceDependency
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


@router.get(
    "/{project_id}/events",
    response_model=None,
    summary="订阅项目实时事件",
    description="先回放未消费的数据库事件，再持续推送新事件，并支持 Last-Event-ID 续传。",
)
async def stream_project_events(
    project_id: str,
    service: EventServiceDependency,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    await service.ensure_project_exists(project_id)
    after_sequence = await service.resolve_after_sequence(project_id, last_event_id)
    event_stream = service.stream(project_id, after_sequence)

    async def generate_events() -> AsyncIterator[dict[str, str]]:
        async for event in event_stream:
            if event is None:
                yield {"comment": "heartbeat"}
                continue
            yield {
                "id": event.event_id,
                "event": event.event_type,
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(
        generate_events(),
        ping=None,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除研究项目",
    description="删除指定项目及其关联数据。",
)
async def delete_project(project_id: str, service: ProjectServiceDependency) -> None:
    await service.delete_project(project_id)
