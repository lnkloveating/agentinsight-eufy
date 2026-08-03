from fastapi import APIRouter

from app.schemas.system import HealthResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return the only implemented endpoint in the initial skeleton."""
    return HealthResponse(status="ok", version="0.1.0")
