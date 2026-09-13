from typing import Any

from langgraph.graph import MessagesState

from app.agent.schemas import AgentAction, AgentIntent, EvidenceStatus


class AgentState(MessagesState, total=False):
    """LangGraph 节点之间共享的最小 Agent 状态。"""

    original_query: str
    current_query: str

    intent: AgentIntent | None
    allow_web: bool
    requires_freshness: bool

    kb_results: list[dict[str, Any]]
    web_results: list[dict[str, Any]]
    article_contents: list[dict[str, Any]]
    web_page_contents: list[dict[str, Any]]

    selected_evidence: list[dict[str, Any]]
    evidence_status: EvidenceStatus
    evidence_reason: str | None

    rewrite_count: int
    step_count: int
    tool_call_counts: dict[str, int]
    allowed_actions: list[AgentAction]
    next_action: AgentAction | None

    last_tool_error: str | None

    final_answer: str | None
    sources: list[dict[str, Any]]
