from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


app = FastAPI(title="GistAI API")


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """返回服务健康状态。"""

    return HealthResponse(status="ok")
