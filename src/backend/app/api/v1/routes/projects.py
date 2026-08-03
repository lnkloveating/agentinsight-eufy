from typing import NoReturn

from fastapi import APIRouter, HTTPException, status

from app.schemas.project import DecisionCreate, Project, ProjectCreate

router = APIRouter()


def not_implemented() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Contract scaffold only; business implementation is pending.",
    )


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate) -> Project:
    del payload
    not_implemented()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str) -> Project:
    del project_id
    not_implemented()


@router.get("/{project_id}/events", response_model=None)
async def stream_project_events(project_id: str) -> None:
    del project_id
    not_implemented()


@router.post("/{project_id}/decisions", response_model=Project, status_code=status.HTTP_202_ACCEPTED)
async def submit_decision(project_id: str, payload: DecisionCreate) -> Project:
    del project_id, payload
    not_implemented()
