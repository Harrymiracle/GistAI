from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


AgentMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class AgentResponseStatus(StrEnum):
    """前端可直接使用的 Agent 回答状态。"""

    ANSWER = "answer"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    ERROR = "error"


class AgentChatRequest(BaseModel):
    """Agent Chat 的最小客户端输入。"""

    model_config = ConfigDict(extra="forbid")

    message: AgentMessage
    thread_id: UUID | None = None
    allow_web_override: Annotated[bool, Field(strict=True)] | None = None


class AgentSource(BaseModel):
    """隐藏内部证据结构的统一来源契约。"""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["knowledge_base", "web"]
    title: str
    article_id: int | None = None
    chunk_id: int | None = None
    url: str | None = None
    source: str | None = None
    published_at: str | None = None


class AgentChatData(BaseModel):
    """一次 Agent Chat 调用返回给前端的数据。"""

    model_config = ConfigDict(extra="forbid")

    thread_id: UUID
    answer: str
    status: AgentResponseStatus
    sources: list[AgentSource]
