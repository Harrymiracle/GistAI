from collections.abc import Sequence
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.schemas import AgentAction, EvidenceStatus, KnowledgeSearchInput
from app.agent.state import AgentState


MAX_REWRITES = 1
INSUFFICIENT_ANSWER = "当前知识库中没有足够可靠的证据，无法回答这个问题。"
FAILED_ANSWER = "当前无法从知识库获得可靠证据，请稍后重试。"
PARTIAL_GAP_NOTICE = "其余内容无法根据当前知识库确认。"


def _latest_user_query(messages: Sequence[BaseMessage]) -> str:
    """从规范化消息中读取最近一条文本形式的用户问题。"""

    for message in reversed(messages):
        if message.type == "human" and isinstance(message.content, str):
            query = message.content.strip()
            if query:
                return query
    raise ValueError("Agent 输入缺少有效的用户问题")


def initialize(state: AgentState) -> dict[str, object]:
    """保留对话消息，并为最新用户问题重置全部单轮运行态。"""

    query = _latest_user_query(state["messages"])
    return {
        "original_query": query,
        "current_query": query,
        "intent": None,
        "allow_web": False,
        "requires_freshness": False,
        "kb_results": [],
        "web_results": [],
        "article_contents": [],
        "web_page_contents": [],
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.UNKNOWN,
        "evidence_reason": None,
        "rewrite_count": 0,
        "step_count": 0,
        "tool_call_counts": {},
        "allowed_actions": [],
        "next_action": None,
        "last_tool_error": None,
        "final_answer": None,
        "sources": [],
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


def evaluate_and_decide(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """计算动作白名单，并校验模型给出的证据决策。"""

    allowed_actions = _allowed_actions(state)
    if state.get("last_tool_error"):
        return _insufficient_decision(
            allowed_actions,
            "知识库检索执行失败，无法评估证据。",
        )
    if allowed_actions == [AgentAction.INSUFFICIENT]:
        return _insufficient_decision(
            allowed_actions,
            "查询改写次数已用尽，仍未找到可用证据。",
        )

    try:
        decision = runtime.context.reasoning.decide(
            original_query=state["original_query"],
            current_query=state["current_query"],
            evidence=list(state.get("kb_results", [])),
            allowed_actions=allowed_actions,
            conversation=state["messages"],
        )
        if decision.next_action not in allowed_actions:
            raise ValueError("模型选择了未授权动作")
        if decision.next_action is AgentAction.ANSWER:
            if decision.evidence_status not in {
                EvidenceStatus.SUFFICIENT,
                EvidenceStatus.PARTIAL,
            }:
                raise ValueError("回答动作与证据状态不一致")
            selected_evidence = _select_evidence(
                list(state.get("kb_results", [])),
                decision.selected_result_indexes,
            )
            if not selected_evidence:
                raise ValueError("回答动作缺少有效证据")
        elif decision.next_action is AgentAction.REWRITE_QUERY:
            if decision.evidence_status not in {
                EvidenceStatus.PARTIAL,
                EvidenceStatus.INSUFFICIENT,
            }:
                raise ValueError("改写动作与证据状态不一致")
            selected_evidence = []
        else:
            if decision.evidence_status is not EvidenceStatus.INSUFFICIENT:
                raise ValueError("终止动作与证据状态不一致")
            selected_evidence = []
    except Exception as exc:
        return {
            **_insufficient_decision(
                allowed_actions,
                "Agent 无法生成有效的证据决策。",
            ),
            "last_tool_error": f"Agent 决策失败（{type(exc).__name__}）",
        }

    return {
        "allowed_actions": allowed_actions,
        "selected_evidence": selected_evidence,
        "evidence_status": decision.evidence_status,
        "evidence_reason": decision.reason,
        "next_action": decision.next_action,
        "last_tool_error": None,
    }


def rewrite_query(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """在程序硬限制内生成一个新的知识库检索查询。"""

    rewrite_count = state.get("rewrite_count", 0)
    if rewrite_count >= MAX_REWRITES:
        return {
            **_insufficient_decision(
                [AgentAction.INSUFFICIENT],
                "查询改写次数已达到上限。",
            ),
            "last_tool_error": "Query Rewrite 被程序限制拒绝",
        }

    update: dict[str, object] = {
        "rewrite_count": rewrite_count + 1,
        "step_count": state.get("step_count", 0) + 1,
    }
    try:
        rewritten_query = runtime.context.reasoning.rewrite_query(
            original_query=state["original_query"],
            current_query=state["current_query"],
            conversation=state["messages"],
        )
        if rewritten_query.strip() == state["current_query"].strip():
            raise ValueError("改写查询与当前查询相同")
    except Exception as exc:
        update.update(
            _insufficient_decision(
                [AgentAction.INSUFFICIENT],
                "无法生成有效的查询改写。",
            )
        )
        update["last_tool_error"] = (
            f"Query Rewrite 执行失败（{type(exc).__name__}）"
        )
        return update

    update.update(
        current_query=rewritten_query,
        kb_results=[],
        selected_evidence=[],
        evidence_status=EvidenceStatus.UNKNOWN,
        evidence_reason=None,
        next_action=AgentAction.KNOWLEDGE_SEARCH,
        last_tool_error=None,
    )
    return update


def generate_answer(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """只使用程序选中的证据回答最初问题。"""

    selected_evidence = list(state.get("selected_evidence", []))
    if not selected_evidence:
        return _answer_update(INSUFFICIENT_ANSWER, [], "回答缺少有效证据")
    try:
        answer = runtime.context.reasoning.generate_answer(
            original_query=state["original_query"],
            evidence=selected_evidence,
            evidence_status=state["evidence_status"],
            conversation=state["messages"],
        )
    except Exception as exc:
        return _answer_update(
            FAILED_ANSWER,
            [],
            f"Agent 回答生成失败（{type(exc).__name__}）",
        )

    if state["evidence_status"] is EvidenceStatus.PARTIAL:
        answer = f"{answer}\n\n{PARTIAL_GAP_NOTICE}"
    sources = [
        {
            "article_id": item["article_id"],
            "chunk_id": item["chunk_id"],
            "title": item.get("title"),
        }
        for item in selected_evidence
    ]
    return _answer_update(answer, sources, None)


def generate_insufficient_answer(state: AgentState) -> dict[str, object]:
    """以确定性模板结束无可靠证据或依赖失败的运行。"""

    answer = FAILED_ANSWER if state.get("last_tool_error") else INSUFFICIENT_ANSWER
    return _answer_update(answer, [], state.get("last_tool_error"))


def route_after_decision(
    state: AgentState,
) -> Literal["generate_answer", "rewrite_query", "insufficient_answer"]:
    """只依据已校验的 next_action 选择下一节点。"""

    if state.get("next_action") is AgentAction.ANSWER:
        return "generate_answer"
    if state.get("next_action") is AgentAction.REWRITE_QUERY:
        return "rewrite_query"
    return "insufficient_answer"


def route_after_rewrite(
    state: AgentState,
) -> Literal["knowledge_search", "insufficient_answer"]:
    """改写失败时安全终止，成功时重新检索。"""

    if state.get("next_action") is AgentAction.KNOWLEDGE_SEARCH:
        return "knowledge_search"
    return "insufficient_answer"


def _allowed_actions(state: AgentState) -> list[AgentAction]:
    if state.get("last_tool_error"):
        return [AgentAction.INSUFFICIENT]
    has_evidence = bool(state.get("kb_results"))
    can_rewrite = state.get("rewrite_count", 0) < MAX_REWRITES
    if not has_evidence:
        if can_rewrite:
            return [AgentAction.REWRITE_QUERY, AgentAction.INSUFFICIENT]
        return [AgentAction.INSUFFICIENT]
    actions = [AgentAction.ANSWER]
    if can_rewrite:
        actions.append(AgentAction.REWRITE_QUERY)
    actions.append(AgentAction.INSUFFICIENT)
    return actions


def _select_evidence(
    candidates: list[dict[str, object]],
    indexes: list[int],
) -> list[dict[str, object]]:
    if not indexes or any(index >= len(candidates) for index in indexes):
        return []
    return [candidates[index] for index in dict.fromkeys(indexes)]


def _insufficient_decision(
    allowed_actions: list[AgentAction],
    reason: str,
) -> dict[str, object]:
    return {
        "allowed_actions": allowed_actions,
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.INSUFFICIENT,
        "evidence_reason": reason,
        "next_action": AgentAction.INSUFFICIENT,
    }


def _answer_update(
    answer: str,
    sources: list[dict[str, object]],
    error: str | None,
) -> dict[str, object]:
    return {
        "final_answer": answer,
        "sources": sources,
        "last_tool_error": error,
        "messages": [AIMessage(content=answer)],
    }
