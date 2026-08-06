"""FastAPI 依赖注入。"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.events import EventService, ProjectEventBroker
from app.application.evidence import EvidenceQueryService
from app.application.projects import ProjectService
from app.core.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.repositories import ProjectRepository


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session() as session:
        yield session


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_project_service(request: Request, session: SessionDependency) -> ProjectService:
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return ProjectService(ProjectRepository(session), trace_id, request.app.state.event_broker)


ProjectServiceDependency = Annotated[ProjectService, Depends(get_project_service)]


def get_event_service(request: Request) -> EventService:
    database: Database = request.app.state.database
    broker: ProjectEventBroker = request.app.state.event_broker
    settings: Settings = request.app.state.settings
    return EventService(database, broker, settings.sse_heartbeat_seconds)


EventServiceDependency = Annotated[EventService, Depends(get_event_service)]


def get_evidence_query_service(session: SessionDependency) -> EvidenceQueryService:
    return EvidenceQueryService(EvidenceRepository(session))


EvidenceQueryServiceDependency = Annotated[
    EvidenceQueryService, Depends(get_evidence_query_service)
]
