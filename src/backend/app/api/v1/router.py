from fastapi import APIRouter

from app.api.v1.routes import (
    competitor_discovery,
    competitor_material_discovery,
    competitor_source_onboarding,
    concepts,
    evidence,
    health,
    models,
    projects,
    reports,
    research,
    runtimes,
    source_discovery,
    source_requirements,
    sources,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(models.router, prefix="/models", tags=["Models"])
api_router.include_router(runtimes.router, prefix="/runtimes", tags=["Runtimes"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(research.router, prefix="/projects", tags=["Research"])
api_router.include_router(competitor_discovery.router, prefix="/projects", tags=["Research"])
api_router.include_router(
    competitor_material_discovery.router, prefix="/projects", tags=["Evidence"]
)
api_router.include_router(
    competitor_source_onboarding.router, prefix="/projects", tags=["Evidence"]
)
api_router.include_router(evidence.router, prefix="/projects", tags=["Evidence"])
api_router.include_router(source_discovery.router, prefix="/projects", tags=["Evidence"])
api_router.include_router(source_requirements.router, prefix="/projects", tags=["Evidence"])
api_router.include_router(sources.router, prefix="/projects", tags=["Evidence"])
api_router.include_router(concepts.router, prefix="/projects", tags=["Innovations"])
api_router.include_router(reports.router, prefix="/projects", tags=["Reports"])
