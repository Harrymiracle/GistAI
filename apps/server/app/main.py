from fastapi import FastAPI
from pydantic import BaseModel

from app.api.v1.router import api_router
from app.core.handlers import register_exception_handlers


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


app = FastAPI(title="GistAI API")
register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """返回服务健康状态。"""

    return HealthResponse(status="ok")
