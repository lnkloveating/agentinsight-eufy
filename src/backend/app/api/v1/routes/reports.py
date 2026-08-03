from fastapi import APIRouter

from app.api.v1.routes.projects import not_implemented
from app.schemas.report import Metrics, Report

router = APIRouter()


@router.get("/{project_id}/report", response_model=Report)
async def get_report(project_id: str) -> Report:
    del project_id
    not_implemented()


@router.get("/{project_id}/metrics", response_model=Metrics)
async def get_metrics(project_id: str) -> Metrics:
    del project_id
    not_implemented()
