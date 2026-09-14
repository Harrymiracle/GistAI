from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from app.agent.chat import AgentChatService
from app.agent.checkpoint import postgres_checkpointer
from app.agent.graph import create_agent_graph
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.handlers import register_exception_handlers


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """在应用生命周期内复用并关闭 PostgreSQL checkpoint 连接池。"""

    with postgres_checkpointer(settings.database_url) as checkpointer:
        graph = create_agent_graph(checkpointer)
        application.state.agent_chat_service = AgentChatService(graph)
        yield


app = FastAPI(title="GistAI API", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """返回服务健康状态。"""

    return HealthResponse(status="ok")
