"""后端应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
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
from app.application.runtime import (
    ExternalCliProcessRunner,
    ExternalRuntimeCatalog,
    OpenCodeCliDriver,
)
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import TraceIdMiddleware
from app.infrastructure.database import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建供测试、开发和生产环境复用的 FastAPI 应用。"""
    resolved_settings = settings or get_settings()
    credential_resolver = (
        EnvironmentCredentialResolver.from_dotenv(
            resolved_settings.model_credentials_env_file
        )
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
            OpenAICompatibleProvider(
                provider_config.provider_id, provider_config.base_url
            )
        )
    prompt_registry = PromptRegistry()
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
        if resolved_settings.auto_create_schema:
            await database.create_schema()
        try:
            yield
        finally:
            await database.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="有证据、有反方、有淘汰、有人类决策的 AI 原生产品定义平台。",
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
    application.state.opencode_driver = opencode_driver
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
