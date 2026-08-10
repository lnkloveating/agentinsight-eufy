"""后端应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.competitor import (
    CompetitorA2ASupervisorAdapter,
    CompetitorDiscoveryModelAgentAdapter,
    CompetitorEcosystemModelAdapter,
    CompetitorSynthesisModelAdapter,
    CompetitorUserReviewModelSpecialistAdapter,
    OfficialProductModelSpecialistAdapter,
    PriceChannelModelSpecialistAdapter,
    register_competitor_discovery_prompt,
    register_competitor_ecosystem_prompt,
    register_competitor_synthesis_prompt,
    register_competitor_user_review_prompt,
    register_official_product_prompt,
    register_price_channel_prompt,
)
from app.agents.product_technical import (
    ProductTechnicalModelAgentAdapter,
    register_product_technical_prompt,
)
from app.agents.user_research import UserResearchModelAgentAdapter
from app.agents.user_research.prompt import register_user_research_prompt
from app.api.v1.router import api_router
from app.application.brief_clarification import register_brief_clarifier_prompt
from app.application.events import ProjectEventBroker
from app.application.model_gateway import (
    EnvironmentCredentialResolver,
    ModelCatalog,
    ModelGateway,
    ModelProviderRegistry,
    OpenAICompatibleProvider,
    PromptRegistry,
    parse_openai_compatible_provider_configs,
)
from app.application.model_gateway.selection import ProjectModelSelectionResolver
from app.application.runtime import (
    AgentRegistry,
    ExternalCliProcessRunner,
    ExternalRuntimeCatalog,
    OpenCodeCliDriver,
)
from app.application.source_routing import register_source_routing_prompt
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import TraceIdMiddleware
from app.infrastructure.database import Database
from app.integrations.a2a import (
    A2ASpecialistRegistry,
    CompetitorA2AGateway,
    CompetitorSpecialistType,
)
from app.sources.search_discovery import (
    SearchDiscoveryRegistry,
    TavilySearchDiscoveryConnector,
)
from app.sources.web_connector import SafeHttpWebConnector
from app.workflows.contracts import ResearchAgentType


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建供测试、开发和生产环境复用的 FastAPI 应用。"""
    resolved_settings = settings or get_settings()
    credential_resolver = (
        EnvironmentCredentialResolver.from_dotenv(resolved_settings.model_credentials_env_file)
        if resolved_settings.model_credentials_env_file is not None
        else EnvironmentCredentialResolver()
    )
    model_catalog = ModelCatalog.from_json(
        resolved_settings.model_catalog_json,
        default_model_id=resolved_settings.default_model_id,
    )
    model_provider_registry = ModelProviderRegistry()
    for provider_config in parse_openai_compatible_provider_configs(
        resolved_settings.openai_compatible_providers_json
    ):
        model_provider_registry.register(
            OpenAICompatibleProvider(provider_config.provider_id, provider_config.base_url)
        )
    prompt_registry = PromptRegistry()
    register_brief_clarifier_prompt(prompt_registry)
    register_user_research_prompt(prompt_registry)
    register_product_technical_prompt(prompt_registry)
    register_competitor_discovery_prompt(prompt_registry)
    register_competitor_ecosystem_prompt(prompt_registry)
    register_competitor_synthesis_prompt(prompt_registry)
    register_competitor_user_review_prompt(prompt_registry)
    register_official_product_prompt(prompt_registry)
    register_price_channel_prompt(prompt_registry)
    register_source_routing_prompt(prompt_registry)
    external_cli_process_runner = ExternalCliProcessRunner(
        max_output_bytes=resolved_settings.external_cli_max_output_bytes,
        probe_timeout_seconds=resolved_settings.external_cli_probe_timeout_seconds,
    )
    opencode_driver = OpenCodeCliDriver(
        executable=resolved_settings.opencode_executable,
        provider_id=resolved_settings.opencode_provider_id,
        provider_name=resolved_settings.opencode_provider_name,
        provider_base_url=resolved_settings.opencode_provider_base_url,
        provider_model=resolved_settings.opencode_provider_model,
        credential_env=resolved_settings.opencode_credential_env,
        enabled=resolved_settings.opencode_runtime_enabled,
    )
    external_runtime_catalog = ExternalRuntimeCatalog(
        (opencode_driver,), credential_resolver, external_cli_process_runner
    )
    search_discovery_registry = SearchDiscoveryRegistry(
        (
            TavilySearchDiscoveryConnector(
                credential_resolver.resolve(
                    resolved_settings.search_discovery_tavily_credential_env
                ),
                enabled=resolved_settings.search_discovery_enabled,
                timeout_seconds=resolved_settings.search_discovery_timeout_seconds,
                max_response_bytes=resolved_settings.search_discovery_max_response_bytes,
            ),
        )
    )
    web_connector = (
        SafeHttpWebConnector(
            user_agent=resolved_settings.web_connector_user_agent,
            timeout_seconds=resolved_settings.web_connector_timeout_seconds,
            max_response_bytes=resolved_settings.web_connector_max_response_bytes,
            max_redirects=resolved_settings.web_connector_max_redirects,
            respect_robots_txt=resolved_settings.web_connector_respect_robots_txt,
            allowed_domains=tuple(resolved_settings.web_connector_allowed_domains),
        )
        if resolved_settings.web_connector_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved_settings.database_url)
        application.state.database = database
        application.state.event_broker = ProjectEventBroker()
        application.state.model_gateway = ModelGateway(
            database,
            model_catalog,
            credential_resolver,
            model_provider_registry,
            max_retries=resolved_settings.model_max_retries,
            retry_base_seconds=resolved_settings.model_retry_base_seconds,
        )
        agent_registry = AgentRegistry()
        competitor_discovery_registry = AgentRegistry()
        competitor_discovery_registry.bind(
            ResearchAgentType.COMPETITOR_RESEARCH,
            CompetitorDiscoveryModelAgentAdapter(
                application.state.model_gateway,
                prompt_registry,
                ProjectModelSelectionResolver(database),
                model_timeout_seconds=(
                    resolved_settings.competitor_discovery_model_timeout_seconds
                ),
            ),
        )
        application.state.competitor_discovery_registry = competitor_discovery_registry
        a2a_specialist_registry = A2ASpecialistRegistry()
        a2a_specialist_registry.bind(
            CompetitorSpecialistType.OFFICIAL_PRODUCT,
            OfficialProductModelSpecialistAdapter(
                application.state.model_gateway,
                prompt_registry,
                ProjectModelSelectionResolver(database),
                model_timeout_seconds=(resolved_settings.competitor_official_model_timeout_seconds),
            ),
        )
        a2a_specialist_registry.bind(
            CompetitorSpecialistType.PRICE_CHANNEL,
            PriceChannelModelSpecialistAdapter(
                application.state.model_gateway,
                prompt_registry,
                ProjectModelSelectionResolver(database),
                model_timeout_seconds=(resolved_settings.competitor_price_model_timeout_seconds),
            ),
        )
        a2a_specialist_registry.bind(
            CompetitorSpecialistType.USER_REVIEW,
            CompetitorUserReviewModelSpecialistAdapter(
                application.state.model_gateway,
                prompt_registry,
                ProjectModelSelectionResolver(database),
                model_timeout_seconds=(resolved_settings.competitor_review_model_timeout_seconds),
            ),
        )
        application.state.a2a_specialist_registry = a2a_specialist_registry
        application.state.competitor_a2a_gateway = CompetitorA2AGateway(
            database,
            a2a_specialist_registry,
            application.state.event_broker,
            specialist_timeout_seconds=(
                resolved_settings.competitor_a2a_specialist_timeout_seconds
            ),
        )
        agent_registry.bind(
            ResearchAgentType.USER_RESEARCH,
            UserResearchModelAgentAdapter(
                application.state.model_gateway,
                prompt_registry,
                ProjectModelSelectionResolver(database),
            ),
        )
        agent_registry.bind(
            ResearchAgentType.COMPETITOR_RESEARCH,
            CompetitorA2ASupervisorAdapter(
                application.state.competitor_a2a_gateway,
                CompetitorSynthesisModelAdapter(
                    application.state.model_gateway,
                    prompt_registry,
                    ProjectModelSelectionResolver(database),
                    model_timeout_seconds=(
                        resolved_settings.competitor_synthesis_model_timeout_seconds
                    ),
                ),
                CompetitorEcosystemModelAdapter(
                    application.state.model_gateway,
                    prompt_registry,
                    ProjectModelSelectionResolver(database),
                    model_timeout_seconds=(
                        resolved_settings.competitor_ecosystem_model_timeout_seconds
                    ),
                ),
            ),
        )
        agent_registry.bind(
            ResearchAgentType.PRODUCT_TECHNICAL,
            ProductTechnicalModelAgentAdapter(
                application.state.model_gateway,
                prompt_registry,
                ProjectModelSelectionResolver(database),
                model_timeout_seconds=(
                    resolved_settings.product_technical_model_timeout_seconds
                ),
            ),
        )
        application.state.agent_registry = agent_registry
        if resolved_settings.auto_create_schema:
            await database.create_schema()
        try:
            yield
        finally:
            await database.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="有证据、有反方、有淘汰、有人类决策的 AI 原生家庭安防生态研究平台。",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.model_catalog = model_catalog
    application.state.model_credentials = credential_resolver
    application.state.model_provider_registry = model_provider_registry
    application.state.prompt_registry = prompt_registry
    application.state.external_cli_process_runner = external_cli_process_runner
    application.state.external_runtime_catalog = external_runtime_catalog
    application.state.search_discovery_registry = search_discovery_registry
    application.state.opencode_driver = opencode_driver
    application.state.web_connector = web_connector
    # A production ASR/vision connector must be registered explicitly. The two
    # organizer models currently declare text capabilities only.
    application.state.media_understanding_connector = None
    application.add_middleware(TraceIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-ID"],
    )
    register_error_handlers(application)
    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()


def main() -> None:
    """启动本地开发 API。"""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
