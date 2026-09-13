from collections.abc import Sequence

from langchain_core.messages import BaseMessage
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.schemas import EvidenceStatus, KnowledgeSearchInput
from app.agent.state import AgentState


PLACEHOLDER_ANSWER = "Agent graph initialized successfully."


def _latest_user_query(messages: Sequence[BaseMessage]) -> str:
    """从规范化消息中读取最近一条文本形式的用户问题。"""

    for message in reversed(messages):
        if message.type == "human" and isinstance(message.content, str):
            query = message.content.strip()
            if query:
                return query
    raise ValueError("Agent 输入缺少有效的用户问题")


def initialize(state: AgentState) -> dict[str, object]:
    """初始化骨架运行所需字段，不调用任何外部业务能力。"""

    query = _latest_user_query(state["messages"])
    return {
        "original_query": state.get("original_query") or query,
        "current_query": query,
        "intent": state.get("intent"),
        "allow_web": state.get("allow_web", False),
        "requires_freshness": state.get("requires_freshness", False),
        "kb_results": list(state.get("kb_results", [])),
        "web_results": list(state.get("web_results", [])),
        "article_contents": list(state.get("article_contents", [])),
        "web_page_contents": list(state.get("web_page_contents", [])),
        "selected_evidence": list(state.get("selected_evidence", [])),
        "evidence_status": state.get("evidence_status", EvidenceStatus.UNKNOWN),
        "evidence_reason": state.get("evidence_reason"),
        "rewrite_count": state.get("rewrite_count", 0),
        "step_count": state.get("step_count", 0),
        "tool_call_counts": dict(state.get("tool_call_counts", {})),
        "allowed_actions": list(state.get("allowed_actions", [])),
        "next_action": state.get("next_action"),
        "last_tool_error": state.get("last_tool_error"),
        "sources": list(state.get("sources", [])),
    }


def knowledge_search(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """调用现有知识库检索能力并写入最小候选证据。"""

    payload = KnowledgeSearchInput(
        query=state["current_query"],
        top_k=runtime.context.top_k,
    )
    tool_call_counts = dict(state.get("tool_call_counts", {}))
    tool_call_counts["knowledge_search"] = (
        tool_call_counts.get("knowledge_search", 0) + 1
    )
    update: dict[str, object] = {
        "step_count": state.get("step_count", 0) + 1,
        "tool_call_counts": tool_call_counts,
    }
    try:
        results = runtime.context.knowledge_search.search(payload)
    except Exception as exc:
        update.update(
            kb_results=[],
            last_tool_error=(
                f"Knowledge Search 执行失败（{type(exc).__name__}）"
            ),
        )
        return update

    update.update(
        kb_results=[result.model_dump(mode="json") for result in results],
        last_tool_error=None,
    )
    return update


def finish(_state: AgentState) -> dict[str, str]:
    """写入用于验证最小图闭环的占位回答。"""

    return {"final_answer": PLACEHOLDER_ANSWER}
