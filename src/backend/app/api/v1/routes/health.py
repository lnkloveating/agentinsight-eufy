from fastapi import APIRouter

from app.schemas.system import HealthResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="检查服务健康状态",
    description="供前端、容器和监控系统确认 API 进程是否可用。",
)
async def get_health() -> HealthResponse:
    """返回服务版本与健康状态。"""
    return HealthResponse(status="ok", version="0.2.0")
