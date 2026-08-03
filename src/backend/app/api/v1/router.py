from fastapi import APIRouter

from app.api.v1.routes import concepts, evidence, health, projects, reports

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(evidence.router, prefix="/projects", tags=["Evidence"])
api_router.include_router(concepts.router, prefix="/projects", tags=["Concepts"])
api_router.include_router(reports.router, prefix="/projects", tags=["Reports"])
