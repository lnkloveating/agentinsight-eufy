"""FastAPI 依赖注入。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.events import EventService, ProjectEventBroker
from app.application.evidence import EvidenceQueryService
from app.application.innovations import InnovationService
from app.application.model_gateway import CredentialResolver, ModelCatalog
from app.application.projects import ProjectService
from app.application.sources import SourceAssetService
from app.core.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.innovation_repository import InnovationRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.infrastructure.source_storage import LocalSourceStorage


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session() as session:
        yield session


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_project_service(request: Request, session: SessionDependency) -> ProjectService:
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return ProjectService(
        ProjectRepository(session),
        trace_id,
        request.app.state.event_broker,
        cast(ModelCatalog, request.app.state.model_catalog),
    )


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


def get_source_asset_service(
    request: Request, session: SessionDependency
) -> SourceAssetService:
    settings: Settings = request.app.state.settings
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return SourceAssetService(
        SourceAssetRepository(session),
        ProjectRepository(session),
        LocalSourceStorage(
            Path(settings.source_storage_root),
            settings.source_max_upload_bytes,
        ),
        trace_id,
        request.app.state.event_broker,
    )


SourceAssetServiceDependency = Annotated[
    SourceAssetService, Depends(get_source_asset_service)
]


def get_innovation_service(request: Request, session: SessionDependency) -> InnovationService:
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return InnovationService(
        InnovationRepository(session),
        EvidenceRepository(session),
        ProjectRepository(session),
        trace_id,
        request.app.state.event_broker,
    )


InnovationServiceDependency = Annotated[InnovationService, Depends(get_innovation_service)]


def get_model_catalog(request: Request) -> ModelCatalog:
    return cast(ModelCatalog, request.app.state.model_catalog)


ModelCatalogDependency = Annotated[ModelCatalog, Depends(get_model_catalog)]


def get_model_credentials(request: Request) -> CredentialResolver:
    return cast(CredentialResolver, request.app.state.model_credentials)


ModelCredentialDependency = Annotated[
    CredentialResolver, Depends(get_model_credentials)
]
