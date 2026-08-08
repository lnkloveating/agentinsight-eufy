"""FastAPI 依赖注入。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.user_research.context import UserResearchEvidenceContextBuilder
from app.application.events import EventService, ProjectEventBroker
from app.application.evidence import EvidenceQueryService, SourceEvidencePromotionService
from app.application.innovations import InnovationService
from app.application.model_gateway import (
    CredentialResolver,
    ModelCatalog,
    ModelGateway,
    PromptRegistry,
)
from app.application.model_gateway.selection import ProjectModelSelectionResolver
from app.application.projects import ProjectService
from app.application.research import UserResearchService
from app.application.runtime import AgentRegistry, AgentRuntimeGateway, ExternalRuntimeCatalog
from app.application.source_discovery import SearchDiscoveryService
from app.application.source_requirements import SourceRequirementService
from app.application.source_routing import SourceRoutingService
from app.application.sources import SourceAssetService, SourceProcessingService
from app.core.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.innovation_repository import InnovationRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.infrastructure.source_processing_workspace import SourceProcessingWorkspaceManager
from app.infrastructure.source_storage import LocalSourceStorage
from app.sources.media_processing import (
    MediaUnderstandingConnector,
    PyAvMediaProcessor,
)
from app.sources.parsers import default_source_parser_registry
from app.sources.search_discovery import SearchDiscoveryRegistry
from app.sources.web_connector import WebConnector


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


def get_source_asset_service(request: Request, session: SessionDependency) -> SourceAssetService:
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


SourceAssetServiceDependency = Annotated[SourceAssetService, Depends(get_source_asset_service)]


def get_source_processing_service(
    request: Request, session: SessionDependency
) -> SourceProcessingService:
    settings: Settings = request.app.state.settings
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return SourceProcessingService(
        SourceAssetRepository(session),
        ProjectRepository(session),
        LocalSourceStorage(
            Path(settings.source_storage_root),
            settings.source_max_upload_bytes,
        ),
        SourceProcessingWorkspaceManager(Path(settings.source_processing_workspace_root)),
        default_source_parser_registry(settings.source_processing_max_excerpt_chars),
        web_connector=cast(WebConnector | None, request.app.state.web_connector),
        media_processor=PyAvMediaProcessor(
            max_duration_seconds=settings.media_processing_max_duration_seconds,
            max_streams=settings.media_processing_max_streams,
            frame_interval_seconds=settings.media_processing_frame_interval_seconds,
            max_frames=settings.media_processing_max_frames,
            max_frame_dimension=settings.media_processing_max_frame_dimension,
            max_decoded_video_frames=(settings.media_processing_max_decoded_video_frames),
            audio_sample_rate=settings.media_processing_audio_sample_rate,
            max_audio_bytes=settings.media_processing_max_audio_bytes,
        ),
        media_understanding_connector=cast(
            MediaUnderstandingConnector | None,
            request.app.state.media_understanding_connector,
        ),
        max_input_bytes=settings.source_processing_max_input_bytes,
        max_fragments=settings.source_processing_max_fragments,
        trace_id=trace_id,
        event_broker=request.app.state.event_broker,
    )


SourceProcessingServiceDependency = Annotated[
    SourceProcessingService, Depends(get_source_processing_service)
]


def get_source_routing_service(request: Request) -> SourceRoutingService:
    settings: Settings = request.app.state.settings
    database: Database = request.app.state.database
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return SourceRoutingService(
        database,
        cast(ModelGateway, request.app.state.model_gateway),
        cast(PromptRegistry, request.app.state.prompt_registry),
        ProjectModelSelectionResolver(database),
        cast(ProjectEventBroker, request.app.state.event_broker),
        trace_id,
        max_fragments=settings.source_routing_max_fragments,
        max_excerpt_chars=settings.source_routing_max_excerpt_chars,
        max_total_chars=settings.source_routing_max_total_chars,
        auto_confirm_threshold=settings.source_routing_auto_confirm_threshold,
        model_timeout_seconds=settings.source_routing_model_timeout_seconds,
    )


SourceRoutingServiceDependency = Annotated[
    SourceRoutingService, Depends(get_source_routing_service)
]


def get_source_requirement_service(request: Request) -> SourceRequirementService:
    database: Database = request.app.state.database
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return SourceRequirementService(
        database,
        cast(ProjectEventBroker, request.app.state.event_broker),
        trace_id,
    )


SourceRequirementServiceDependency = Annotated[
    SourceRequirementService, Depends(get_source_requirement_service)
]


def get_search_discovery_service(request: Request) -> SearchDiscoveryService:
    database: Database = request.app.state.database
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return SearchDiscoveryService(
        database,
        cast(SearchDiscoveryRegistry, request.app.state.search_discovery_registry),
        cast(ProjectEventBroker, request.app.state.event_broker),
        trace_id,
    )


SearchDiscoveryServiceDependency = Annotated[
    SearchDiscoveryService, Depends(get_search_discovery_service)
]


def get_source_evidence_promotion_service(
    request: Request, session: SessionDependency
) -> SourceEvidencePromotionService:
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    return SourceEvidencePromotionService(
        SourceAssetRepository(session),
        EvidenceRepository(session),
        ProjectRepository(session),
        trace_id,
        request.app.state.event_broker,
    )


SourceEvidencePromotionServiceDependency = Annotated[
    SourceEvidencePromotionService,
    Depends(get_source_evidence_promotion_service),
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


ModelCredentialDependency = Annotated[CredentialResolver, Depends(get_model_credentials)]


def get_external_runtime_catalog(request: Request) -> ExternalRuntimeCatalog:
    return cast(ExternalRuntimeCatalog, request.app.state.external_runtime_catalog)


ExternalRuntimeCatalogDependency = Annotated[
    ExternalRuntimeCatalog, Depends(get_external_runtime_catalog)
]


def get_user_research_service(request: Request) -> UserResearchService:
    settings: Settings = request.app.state.settings
    database: Database = request.app.state.database
    trace_id = str(getattr(request.state, "trace_id", "trace_unknown"))
    runtime = AgentRuntimeGateway(
        database,
        cast(AgentRegistry, request.app.state.agent_registry),
        cast(ProjectEventBroker, request.app.state.event_broker),
        trace_id,
    )
    context_builder = UserResearchEvidenceContextBuilder(
        database,
        max_items=settings.user_research_max_evidence_items,
        max_excerpt_chars=settings.user_research_max_excerpt_chars,
        max_total_chars=settings.user_research_max_total_evidence_chars,
    )
    return UserResearchService(database, runtime, context_builder)


UserResearchServiceDependency = Annotated[UserResearchService, Depends(get_user_research_service)]
