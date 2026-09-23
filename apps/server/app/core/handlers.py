import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppError


logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """注册统一 API 异常响应。"""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": exc.data,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            {
                "type": error["type"],
                "loc": list(error["loc"]),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": 42200,
                "message": "请求参数校验失败",
                "data": {"errors": errors},
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        logger.exception("数据库操作失败：%s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": 50001,
                "message": "数据库操作失败",
                "data": None,
            },
        )
