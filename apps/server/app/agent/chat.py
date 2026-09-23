import logging
import time
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.agent.context import AgentContext
from app.agent.schemas import AgentErrorType, EvidenceStatus
from app.schemas.agent import (
    AgentChatData,
    AgentResponseStatus,
    AgentSource,
)


logger = logging.getLogger("uvicorn.error")


class AgentGraph(Protocol):
    """Agent Chat 依赖的最小 Graph 调用边界。"""

    def invoke(
        self,
        graph_input: dict[str, Any],
        *,
        config: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]: ...


class AgentChatService:
    """隔离会话并将内部 AgentState 映射为稳定 API 数据。"""

    def __init__(self, graph: AgentGraph) -> None:
        self._graph = graph

    def chat(
        self,
        message: str,
        thread_id: UUID | None,
        *,
        user_id: int,
        context: AgentContext,
        allow_web_override: bool | None = None,
    ) -> AgentChatData:
        public_thread_id = thread_id or uuid4()
        checkpoint_thread_id = f"{user_id}:{public_thread_id}"
        started_at = time.perf_counter()
        outcome = "error"
        try:
            result = self._graph.invoke(
                {
                    "messages": [{"role": "user", "content": message}],
                    "allow_web_override": allow_web_override,
                },
                config={"configurable": {"thread_id": checkpoint_thread_id}},
                context=context,
            )
            response = AgentChatData(
                thread_id=public_thread_id,
                answer=str(
                    result.get("final_answer")
                    or "当前无法完成回答，请稍后重试。"
                ),
                status=_response_status(result),
                sources=_map_sources(result.get("sources", [])),
            )
            outcome = "success"
            return response
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "agent_chat duration_ms=%.2f outcome=%s",
                duration_ms,
                outcome,
            )


def _response_status(result: dict[str, Any]) -> AgentResponseStatus:
    evidence_status = result.get("evidence_status")
    if (
        result.get("last_error_type") in set(AgentErrorType)
        and not result.get("sources")
    ):
        return AgentResponseStatus.ERROR
    if evidence_status == EvidenceStatus.PARTIAL:
        return AgentResponseStatus.PARTIAL
    if evidence_status == EvidenceStatus.SUFFICIENT:
        return AgentResponseStatus.ANSWER
    return AgentResponseStatus.INSUFFICIENT


def _map_sources(raw_sources: object) -> list[AgentSource]:
    if not isinstance(raw_sources, list):
        return []

    sources: list[AgentSource] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        if item.get("source_type") == "web":
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            sources.append(
                AgentSource(
                    source_type="web",
                    title=_source_title(item),
                    url=url,
                    source=_optional_text(item.get("source")),
                    published_at=_optional_text(item.get("published_at")),
                )
            )
            continue

        article_id = item.get("article_id")
        if not isinstance(article_id, int):
            continue
        chunk_id = item.get("chunk_id")
        sources.append(
            AgentSource(
                source_type="knowledge_base",
                title=_source_title(item),
                article_id=article_id,
                chunk_id=chunk_id if isinstance(chunk_id, int) else None,
            )
        )
    return sources


def _source_title(source: dict[str, Any]) -> str:
    title = source.get("title")
    return title.strip() if isinstance(title, str) and title.strip() else "未命名来源"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
