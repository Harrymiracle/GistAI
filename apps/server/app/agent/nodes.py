from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from app.agent.schemas import EvidenceStatus
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


def finish(_state: AgentState) -> dict[str, str]:
    """写入用于验证最小图闭环的占位回答。"""

    return {"final_answer": PLACEHOLDER_ANSWER}
