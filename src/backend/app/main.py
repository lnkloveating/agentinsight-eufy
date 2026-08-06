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
    PromptRegistry,
)
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import TraceIdMiddleware
from app.infrastructure.database import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建供测试、开发和生产环境复用的 FastAPI 应用。"""
    resolved_settings = settings or get_settings()
    credential_resolver = EnvironmentCredentialResolver()
    model_catalog = ModelCatalog.from_json(
        resolved_settings.model_catalog_json,
        default_model_id=resolved_settings.default_model_id,
    )
    model_provider_registry = ModelProviderRegistry()
    prompt_registry = PromptRegistry()

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
