"""Application entry point.

Only startup wiring and contract routes belong here. Business behavior is intentionally
left for later increments.
"""

from fastapi import FastAPI

from app.api.v1.router import api_router


def create_app() -> FastAPI:
    """Create the FastAPI application used by tests and the production server."""
    application = FastAPI(
        title="AgentInsight eufy API",
        version="0.1.0",
        description="AI-native product-definition platform",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()


def main() -> None:
    """Start the local development API."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
