from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    field: str | None = None


def _response(
    *, request: Request, code: str, message: str, status_code: int, field: str | None = None
) -> JSONResponse:
    request_id = str(request.state.request_id)
    content: dict[str, Any] = ErrorEnvelope(
        error=ErrorDetail(code=code, message=message, field=field, request_id=request_id)
    ).model_dump()
    return JSONResponse(status_code=status_code, content=content)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _response(
            request=request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            field=exc.field,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first_error = exc.errors()[0]
        field = ".".join(str(part) for part in first_error["loc"])
        return _response(
            request=request,
            code="request_validation_failed",
            message="请求参数不符合要求",
            status_code=422,
            field=field,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = "资源不存在" if exc.status_code == 404 else "请求处理失败"
        return _response(
            request=request,
            code="not_found" if exc.status_code == 404 else "http_error",
            message=message,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).error(
            "unhandled application error",
            extra={"request_id": str(request.state.request_id), "error_type": type(exc).__name__},
        )
        return _response(
            request=request,
            code="internal_error",
            message="服务暂时不可用，请稍后重试",  # noqa: RUF001
            status_code=500,
        )
