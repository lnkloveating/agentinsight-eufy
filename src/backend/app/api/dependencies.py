"""FastAPI 依赖注入。"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.projects import ProjectService
from app.infrastructure.database.repositories import ProjectRepository


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session() as session:
        yield session


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_project_service(request: Request, session: SessionDependency) -> ProjectService:
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return ProjectService(ProjectRepository(session), trace_id)


ProjectServiceDependency = Annotated[ProjectService, Depends(get_project_service)]
