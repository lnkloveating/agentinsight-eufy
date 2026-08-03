"""统一业务错误与 HTTP 错误响应。"""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """所有 API 错误使用的统一结构。"""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class AppError(Exception):
    """可安全返回给调用方的业务异常。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = dict(details or {})


def _trace_id(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "trace_unknown"))


def register_error_handlers(application: FastAPI) -> None:
    """注册中文错误处理器。"""

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        body = ErrorEnvelope(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            trace_id=_trace_id(request),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        body = ErrorEnvelope(
            code="REQUEST_VALIDATION_FAILED",
            message="请求参数校验失败，请检查字段格式。",
            details={"errors": exc.errors()},
            trace_id=_trace_id(request),
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        body = ErrorEnvelope(
            code="INTERNAL_SERVER_ERROR",
            message="服务器内部错误，请稍后重试。",
            details={},
            trace_id=_trace_id(request),
        )
        return JSONResponse(status_code=500, content=body.model_dump())
