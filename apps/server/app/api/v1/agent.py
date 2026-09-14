import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.chat import AgentChatService
from app.agent.context import AgentContext
from app.api.deps import (
    get_agent_chat_service,
    get_agent_context,
    get_current_user_id,
)
from app.core.exceptions import AgentChatInternalError
from app.schemas.agent import AgentChatData, AgentChatRequest
from app.schemas.common import ApiResponse


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])

CurrentUserId = Annotated[int, Depends(get_current_user_id)]
AgentContextDependency = Annotated[AgentContext, Depends(get_agent_context)]
AgentChatDependency = Annotated[AgentChatService, Depends(get_agent_chat_service)]


@router.post("/chat", response_model=ApiResponse[AgentChatData])
def chat(
    payload: AgentChatRequest,
    user_id: CurrentUserId,
    context: AgentContextDependency,
    service: AgentChatDependency,
) -> ApiResponse[AgentChatData]:
    """执行一次受当前用户隔离的 Agent 对话。"""

    try:
        data = service.chat(
            payload.message,
            payload.thread_id,
            user_id=user_id,
            context=context,
        )
    except Exception as exc:
        logger.error("Agent Chat 执行失败（%s）", type(exc).__name__)
        raise AgentChatInternalError() from exc
    return ApiResponse(code=20000, message="Agent 回答成功", data=data)
