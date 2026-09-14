from collections.abc import Sequence
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentErrorType,
    AgentIntent,
    EvidenceStatus,
    KnowledgeSearchInput,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from app.agent.state import AgentState
from app.agent.web_page_fetch import WebPageValidationError


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
        "article_fulltext_evidence": [],
        "web_fulltext_evidence": [],
        "read_article_ids": [],
        "fetched_web_urls": [],
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.UNKNOWN,
        "evidence_reason": None,
        "rewrite_count": 0,
        "step_count": 0,
        "tool_call_counts": {},
        "allowed_actions": [],
        "next_action": None,
        "selected_article_result_index": None,
        "selected_web_page_result_index": None,
        "last_tool_error": None,
        "last_error_type": None,
        "last_tool_result": None,
        "action_history": [],
        "final_answer": None,
        "sources": [],
    }


def initial_decision(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """在首次证据评估前确定联网许可和时效性要求。"""

    try:
        result = runtime.context.reasoning.classify_intent(
            query=state["original_query"],
            conversation=state["messages"],
        )
    except Exception:
        return {
            "intent": AgentIntent.KNOWLEDGE_BASE_ONLY,
            "allow_web": False,
            "requires_freshness": False,
            "evidence_reason": "无法确认联网意图，已安全限制为仅知识库。",
        }
    return {
        "intent": result.intent,
        "allow_web": result.allow_web,
        "requires_freshness": result.requires_freshness,
        "evidence_reason": result.reason,
    }


def knowledge_search(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """调用现有知识库检索能力并写入最小候选证据。"""

    policy = runtime.context.policy
    if not policy.can_execute(state, AgentAction.KNOWLEDGE_SEARCH):
        return _policy_rejection_update(
            state,
            "knowledge_search",
            "Knowledge Search 未获授权或已达到调用上限。",
        )

    try:
        payload = KnowledgeSearchInput(
            query=state["current_query"],
            top_k=runtime.context.top_k,
        )
    except (TypeError, ValueError):
        return _policy_rejection_update(
            state,
            "knowledge_search",
            "Knowledge Search 输入未通过校验。",
        )
    update = _tool_attempt_update(state, "knowledge_search")
    try:
        results = runtime.context.knowledge_search.search(payload)
    except Exception as exc:
        safe_message = f"Knowledge Search 执行失败（{type(exc).__name__}）"
        update.update(
            kb_results=[],
            **_tool_outcome_update(
                state,
                "knowledge_search",
                ToolExecutionStatus.EXECUTION_ERROR,
                step_count=update["step_count"],
                error_type=AgentErrorType.EXECUTION,
                safe_message=safe_message,
            ),
        )
        return update

    status = ToolExecutionStatus.SUCCESS if results else ToolExecutionStatus.EMPTY
    update.update(
        kb_results=[result.model_dump(mode="json") for result in results],
        **_tool_outcome_update(
            state,
            "knowledge_search",
            status,
            step_count=update["step_count"],
        ),
    )
    return update


def evaluate_and_decide(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """计算动作白名单，并校验模型给出的证据决策。"""

    policy = runtime.context.policy
    policy_outcome = policy.evaluate(state)
    allowed_actions = policy_outcome.allowed_actions
    if policy_outcome.should_terminate:
        return _termination_decision(
            state,
            allowed_actions,
            policy_outcome.termination_action or AgentAction.INSUFFICIENT,
            policy_outcome.reason or "Agent 运行已安全终止。",
        )

    try:
        decision = runtime.context.reasoning.decide(
            original_query=state["original_query"],
            current_query=state["current_query"],
            kb_evidence=list(state.get("kb_results", [])),
            web_evidence=list(state.get("web_results", [])),
            article_fulltext_evidence=list(
                state.get("article_fulltext_evidence", [])
            ),
            web_fulltext_evidence=list(state.get("web_fulltext_evidence", [])),
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
                source_type="knowledge_base",
            ) + _select_evidence(
                list(state.get("web_results", [])),
                decision.selected_web_result_indexes,
                source_type="web",
            ) + _select_evidence(
                list(state.get("article_fulltext_evidence", [])),
                decision.selected_article_content_indexes,
                source_type="knowledge_base_fulltext",
            ) + _select_evidence(
                list(state.get("web_fulltext_evidence", [])),
                decision.selected_web_page_content_indexes,
                source_type="web_fulltext",
            )
            if (
                state.get("requires_freshness")
                and not (
                    decision.selected_web_result_indexes
                    or decision.selected_web_page_content_indexes
                )
            ):
                raise ValueError("时效性问题的回答必须选择 Web Evidence")
            if not selected_evidence:
                raise ValueError("回答动作缺少有效证据")
        elif decision.next_action is AgentAction.REWRITE_QUERY:
            if decision.evidence_status not in {
                EvidenceStatus.PARTIAL,
                EvidenceStatus.INSUFFICIENT,
            }:
                raise ValueError("改写动作与证据状态不一致")
            selected_evidence = []
        elif decision.next_action is AgentAction.WEB_SEARCH:
            if decision.evidence_status not in {
                EvidenceStatus.PARTIAL,
                EvidenceStatus.INSUFFICIENT,
            }:
                raise ValueError("外部搜索动作与证据状态不一致")
            if (
                decision.selected_result_indexes
                or decision.selected_web_result_indexes
            ):
                raise ValueError("外部搜索动作不得预先选择证据")
            selected_evidence = []
        elif decision.next_action is AgentAction.GET_ARTICLE_CONTENT:
            _validate_tool_decision(
                decision,
                selected_index=decision.selected_article_result_index,
                candidates=list(state.get("kb_results", [])),
                already_used=set(state.get("read_article_ids", [])),
                identity_key="article_id",
            )
            selected_evidence = []
        elif decision.next_action is AgentAction.FETCH_WEB_PAGE:
            _validate_tool_decision(
                decision,
                selected_index=decision.selected_web_page_result_index,
                candidates=list(state.get("web_results", [])),
                already_used=set(state.get("fetched_web_urls", [])),
                identity_key="url",
            )
            selected_evidence = []
        else:
            if decision.evidence_status is not EvidenceStatus.INSUFFICIENT:
                raise ValueError("终止动作与证据状态不一致")
            selected_evidence = []
    except Exception as exc:
        safe_message = f"Agent 决策失败（{type(exc).__name__}）"
        termination = policy.terminate(state, "Agent 无法生成有效的证据决策。")
        return {
            **_termination_decision(
                state,
                allowed_actions,
                termination.termination_action or AgentAction.INSUFFICIENT,
                termination.reason or "Agent 无法生成有效的证据决策。",
            ),
            "last_tool_error": safe_message,
            "last_error_type": AgentErrorType.REASONING,
        }

    return {
        "allowed_actions": allowed_actions,
        "selected_evidence": selected_evidence,
        "evidence_status": decision.evidence_status,
        "evidence_reason": decision.reason,
        "next_action": decision.next_action,
        "selected_article_result_index": decision.selected_article_result_index,
        "selected_web_page_result_index": decision.selected_web_page_result_index,
        "last_tool_error": state.get("last_tool_error"),
        "last_error_type": state.get("last_error_type"),
    }


def rewrite_query(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """在程序硬限制内生成一个新的知识库检索查询。"""

    rewrite_count = state.get("rewrite_count", 0)
    if not runtime.context.policy.can_execute(state, AgentAction.REWRITE_QUERY):
        return _reasoning_rejection_update(
            state,
            "Query Rewrite 未获授权或已达到调用上限。",
        )

    step_count = state.get("step_count", 0) + 1
    update: dict[str, object] = {
        "rewrite_count": rewrite_count + 1,
        "step_count": step_count,
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
        update["last_error_type"] = AgentErrorType.REASONING
        update["action_history"] = _append_action_history(
            state,
            "rewrite_query",
            step_count,
            "reasoning_error",
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
        last_error_type=None,
        action_history=_append_action_history(
            state,
            "rewrite_query",
            step_count,
            "success",
        ),
    )
    return update


def web_search(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """在单轮一次的硬预算内获取搜索结果摘要。"""

    if not runtime.context.policy.can_execute(state, AgentAction.WEB_SEARCH):
        return _policy_rejection_update(
            state,
            "web_search",
            "Web Search 未获授权或已达到调用上限。",
        )

    update = _tool_attempt_update(state, "web_search")
    try:
        results = runtime.context.web_search.search(state["current_query"])
    except Exception as exc:
        safe_message = f"Web Search 执行失败（{type(exc).__name__}）"
        update.update(
            web_results=[],
            **_tool_outcome_update(
                state,
                "web_search",
                ToolExecutionStatus.EXECUTION_ERROR,
                step_count=update["step_count"],
                error_type=AgentErrorType.EXECUTION,
                safe_message=safe_message,
            ),
        )
        return update

    status = ToolExecutionStatus.SUCCESS if results else ToolExecutionStatus.EMPTY
    update.update(
        web_results=[result.model_dump(mode="json") for result in results],
        selected_evidence=[],
        evidence_status=EvidenceStatus.UNKNOWN,
        evidence_reason=None,
        next_action=None,
        **_tool_outcome_update(
            state,
            "web_search",
            status,
            step_count=update["step_count"],
        ),
    )
    return update


def get_article_content(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """读取候选知识库文章全文，并只保留有界的相关上下文。"""

    index = state.get("selected_article_result_index")
    candidates = list(state.get("kb_results", []))
    read_ids = list(state.get("read_article_ids", []))
    if (
        not runtime.context.policy.can_execute(
            state,
            AgentAction.GET_ARTICLE_CONTENT,
        )
        or index is None
        or index >= len(candidates)
    ):
        return _policy_rejection_update(
            state,
            "get_article_content",
            "Article Read 未获授权或已达到调用上限。",
        )

    article_id = candidates[index]["article_id"]
    if not isinstance(article_id, int) or article_id in read_ids:
        return _policy_rejection_update(
            state,
            "get_article_content",
            "Article Read 候选无效或已读取。",
        )
    if (
        runtime.context.article_content is None
        or runtime.context.fulltext_selector is None
    ):
        return _policy_rejection_update(
            state,
            "get_article_content",
            "Article Read 运行时依赖不可用。",
        )

    update = {
        **_tool_attempt_update(state, "get_article_content"),
        "read_article_ids": [*read_ids, article_id],
        "selected_article_result_index": None,
    }
    try:
        result = runtime.context.article_content.get(article_id)
    except Exception as exc:
        safe_message = f"Article Content 执行失败（{type(exc).__name__}）"
        update.update(
            **_tool_outcome_update(
                state,
                "get_article_content",
                ToolExecutionStatus.EXECUTION_ERROR,
                step_count=update["step_count"],
                error_type=AgentErrorType.EXECUTION,
                safe_message=safe_message,
            )
        )
        return update

    article_contents, web_page_contents = _fulltext_selection_inputs(state)
    try:
        if result is not None:
            article_contents.append(result.model_dump(mode="json"))
        article_evidence, web_evidence = runtime.context.fulltext_selector.select(
            query=state["current_query"],
            article_contents=article_contents,
            web_page_contents=web_page_contents,
        )
    except Exception as exc:
        safe_message = f"Article Content 处理失败（{type(exc).__name__}）"
        update.update(
            article_contents=[],
            web_page_contents=[],
            **_tool_outcome_update(
                state,
                "get_article_content",
                ToolExecutionStatus.EXECUTION_ERROR,
                step_count=update["step_count"],
                error_type=AgentErrorType.EXECUTION,
                safe_message=safe_message,
            ),
        )
        return update
    status = (
        ToolExecutionStatus.SUCCESS
        if result is not None
        else ToolExecutionStatus.EMPTY
    )
    update.update(
        article_contents=[],
        web_page_contents=[],
        article_fulltext_evidence=article_evidence,
        web_fulltext_evidence=web_evidence,
        selected_evidence=[],
        evidence_status=EvidenceStatus.UNKNOWN,
        evidence_reason=(
            None if result is not None else "候选文章不存在或当前不可用。"
        ),
        next_action=None,
        **_tool_outcome_update(
            state,
            "get_article_content",
            status,
            step_count=update["step_count"],
        ),
    )
    return update


def fetch_web_page(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """抓取已搜索 URL 的全文，并只保留有界的相关上下文。"""

    index = state.get("selected_web_page_result_index")
    candidates = list(state.get("web_results", []))
    fetched_urls = list(state.get("fetched_web_urls", []))
    if (
        not runtime.context.policy.can_execute(state, AgentAction.FETCH_WEB_PAGE)
        or index is None
        or index >= len(candidates)
    ):
        return _policy_rejection_update(
            state,
            "fetch_web_page",
            "Web Page Fetch 未获授权或已达到调用上限。",
        )

    url = str(candidates[index]["url"])
    if url in fetched_urls:
        return _policy_rejection_update(
            state,
            "fetch_web_page",
            "Web Page Fetch 候选无效或已读取。",
        )
    if (
        runtime.context.web_page_fetch is None
        or runtime.context.fulltext_selector is None
    ):
        return _policy_rejection_update(
            state,
            "fetch_web_page",
            "Web Page Fetch 运行时依赖不可用。",
        )

    try:
        result = runtime.context.web_page_fetch.fetch(url)
    except WebPageValidationError:
        return _policy_rejection_update(
            state,
            "fetch_web_page",
            "Web Page Fetch 地址未通过安全校验。",
        )
    except Exception as exc:
        update = _tool_attempt_update(state, "fetch_web_page")
        safe_message = f"Web Page Fetch 执行失败（{type(exc).__name__}）"
        return {
            **update,
            "fetched_web_urls": [*fetched_urls, url],
            "selected_web_page_result_index": None,
            **_tool_outcome_update(
                state,
                "fetch_web_page",
                ToolExecutionStatus.EXECUTION_ERROR,
                step_count=update["step_count"],
                error_type=AgentErrorType.EXECUTION,
                safe_message=safe_message,
            ),
        }

    update = _tool_attempt_update(state, "fetch_web_page")
    try:
        web_page = result.model_dump(mode="json")
        web_page["title"] = result.title or candidates[index].get("title")
        web_page["source"] = result.source or candidates[index].get("source")
        web_page["published_at"] = (
            web_page.get("published_at") or candidates[index].get("published_at")
        )
        article_contents, web_page_contents = _fulltext_selection_inputs(state)
        web_page_contents.append(web_page)
        article_evidence, web_evidence = runtime.context.fulltext_selector.select(
            query=state["current_query"],
            article_contents=article_contents,
            web_page_contents=web_page_contents,
        )
    except Exception as exc:
        safe_message = f"Web Page Fetch 处理失败（{type(exc).__name__}）"
        return {
            **update,
            "fetched_web_urls": [*fetched_urls, url],
            "selected_web_page_result_index": None,
            **_tool_outcome_update(
                state,
                "fetch_web_page",
                ToolExecutionStatus.EXECUTION_ERROR,
                step_count=update["step_count"],
                error_type=AgentErrorType.EXECUTION,
                safe_message=safe_message,
            ),
        }
    return {
        **update,
        "fetched_web_urls": [*fetched_urls, url],
        "article_contents": [],
        "web_page_contents": [],
        "article_fulltext_evidence": article_evidence,
        "web_fulltext_evidence": web_evidence,
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.UNKNOWN,
        "evidence_reason": None,
        "next_action": None,
        "selected_web_page_result_index": None,
        **_tool_outcome_update(
            state,
            "fetch_web_page",
            ToolExecutionStatus.SUCCESS,
            step_count=update["step_count"],
        ),
    }


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
            AgentErrorType.REASONING,
        )

    if state["evidence_status"] is EvidenceStatus.PARTIAL:
        answer = f"{answer}\n\n{PARTIAL_GAP_NOTICE}"
    sources = [_source_from_evidence(item) for item in selected_evidence]
    return _answer_update(
        answer,
        sources,
        state.get("last_tool_error"),
        state.get("last_error_type"),
    )


def generate_insufficient_answer(state: AgentState) -> dict[str, object]:
    """以确定性模板结束无可靠证据或依赖失败的运行。"""

    answer = FAILED_ANSWER if state.get("last_tool_error") else INSUFFICIENT_ANSWER
    return _answer_update(
        answer,
        [],
        state.get("last_tool_error"),
        state.get("last_error_type"),
    )


def route_after_decision(
    state: AgentState,
) -> Literal[
    "generate_answer",
    "rewrite_query",
    "web_search",
    "get_article_content",
    "fetch_web_page",
    "insufficient_answer",
]:
    """只依据已校验的 next_action 选择下一节点。"""

    if state.get("next_action") in {
        AgentAction.ANSWER,
        AgentAction.PARTIAL_ANSWER,
    }:
        return "generate_answer"
    if state.get("next_action") is AgentAction.REWRITE_QUERY:
        return "rewrite_query"
    if state.get("next_action") is AgentAction.WEB_SEARCH:
        return "web_search"
    if state.get("next_action") is AgentAction.GET_ARTICLE_CONTENT:
        return "get_article_content"
    if state.get("next_action") is AgentAction.FETCH_WEB_PAGE:
        return "fetch_web_page"
    return "insufficient_answer"


def route_after_rewrite(
    state: AgentState,
) -> Literal["knowledge_search", "insufficient_answer"]:
    """改写失败时安全终止，成功时重新检索。"""

    if state.get("next_action") is AgentAction.KNOWLEDGE_SEARCH:
        return "knowledge_search"
    return "insufficient_answer"


def _select_evidence(
    candidates: list[dict[str, object]],
    indexes: list[int],
    *,
    source_type: str,
) -> list[dict[str, object]]:
    if any(index >= len(candidates) for index in indexes):
        raise ValueError("证据索引超出候选范围")
    if not indexes:
        return []
    return [
        {"source_type": source_type, **candidates[index]}
        for index in dict.fromkeys(indexes)
    ]


def _source_from_evidence(item: dict[str, object]) -> dict[str, object]:
    if item["source_type"] in {"web", "web_fulltext"}:
        return {
            "source_type": "web",
            "title": item.get("title"),
            "url": item["url"],
            "source": item["source"],
            "published_at": item.get("published_at"),
        }
    if item["source_type"] == "knowledge_base_fulltext":
        return {
            "article_id": item["article_id"],
            "title": item.get("title"),
        }
    return {
        "article_id": item["article_id"],
        "chunk_id": item["chunk_id"],
        "title": item.get("title"),
    }


def _fulltext_selection_inputs(
    state: AgentState,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """只用已筛选证据重建后续选择输入，避免 checkpoint 保存完整正文。"""

    article_contents = [
        {
            "article_id": item.get("article_id"),
            "title": item.get("title"),
            "clean_content": item["content"],
        }
        for item in state.get("article_fulltext_evidence", [])
    ]
    web_page_contents = [
        {
            "url": item.get("url"),
            "title": item.get("title"),
            "source": item.get("source"),
            "published_at": item.get("published_at"),
            "clean_content": item["content"],
        }
        for item in state.get("web_fulltext_evidence", [])
    ]
    return article_contents, web_page_contents


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


def _termination_decision(
    state: AgentState,
    allowed_actions: list[AgentAction],
    action: AgentAction,
    reason: str,
) -> dict[str, object]:
    selected_evidence = (
        list(state.get("selected_evidence", []))
        if action in {AgentAction.ANSWER, AgentAction.PARTIAL_ANSWER}
        else []
    )
    if action is AgentAction.PARTIAL_ANSWER:
        status = EvidenceStatus.PARTIAL
    elif selected_evidence:
        status = state.get("evidence_status", EvidenceStatus.SUFFICIENT)
    else:
        status = EvidenceStatus.INSUFFICIENT
    return {
        "allowed_actions": allowed_actions,
        "selected_evidence": selected_evidence,
        "evidence_status": status,
        "evidence_reason": reason,
        "next_action": action,
    }


def _validate_tool_decision(
    decision: AgentDecision,
    *,
    selected_index: int | None,
    candidates: list[dict[str, object]],
    already_used: set[object],
    identity_key: str,
) -> None:
    if decision.evidence_status not in {
        EvidenceStatus.PARTIAL,
        EvidenceStatus.INSUFFICIENT,
    }:
        raise ValueError("全文读取动作与证据状态不一致")
    if selected_index is None or selected_index >= len(candidates):
        raise ValueError("全文读取候选索引无效")
    identity = candidates[selected_index].get(identity_key)
    if identity is None or identity in already_used:
        raise ValueError("全文读取候选已使用或缺少标识")
    if (
        decision.selected_result_indexes
        or decision.selected_web_result_indexes
        or decision.selected_article_content_indexes
        or decision.selected_web_page_content_indexes
    ):
        raise ValueError("全文读取动作不得同时选择回答证据")
    if (
        decision.next_action is AgentAction.GET_ARTICLE_CONTENT
        and decision.selected_web_page_result_index is not None
    ):
        raise ValueError("文章读取动作包含无关网页候选")
    if (
        decision.next_action is AgentAction.FETCH_WEB_PAGE
        and decision.selected_article_result_index is not None
    ):
        raise ValueError("网页读取动作包含无关文章候选")


def _answer_update(
    answer: str,
    sources: list[dict[str, object]],
    error: str | None,
    error_type: AgentErrorType | None = None,
) -> dict[str, object]:
    return {
        "final_answer": answer,
        "sources": sources,
        "last_tool_error": error,
        "last_error_type": error_type,
        "messages": [AIMessage(content=answer)],
    }


def _tool_attempt_update(
    state: AgentState,
    tool_name: str,
) -> dict[str, object]:
    """只在真正进入业务 Tool 前增加 step 与调用计数。"""

    tool_call_counts = dict(state.get("tool_call_counts", {}))
    tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1
    return {
        "step_count": state.get("step_count", 0) + 1,
        "tool_call_counts": tool_call_counts,
    }


def _tool_outcome_update(
    state: AgentState,
    tool_name: str,
    status: ToolExecutionStatus,
    *,
    step_count: object,
    error_type: AgentErrorType | None = None,
    safe_message: str | None = None,
) -> dict[str, object]:
    """生成不含原始异常和业务正文的标准 Tool 结果。"""

    result = ToolExecutionResult(
        tool_name=tool_name,
        status=status,
        error_type=error_type,
        safe_message=safe_message,
    )
    history = list(state.get("action_history", []))
    history.append(
        {
            "action": tool_name,
            "step": step_count,
            "outcome": status.value,
        }
    )
    return {
        "last_tool_error": safe_message,
        "last_error_type": error_type,
        "last_tool_result": result.model_dump(mode="python"),
        "action_history": history,
    }


def _policy_rejection_update(
    state: AgentState,
    tool_name: str,
    safe_message: str,
) -> dict[str, object]:
    """拒绝未执行的 Tool 请求，不消耗任何预算。"""

    result = ToolExecutionResult(
        tool_name=tool_name,
        status=ToolExecutionStatus.VALIDATION_ERROR,
        error_type=AgentErrorType.POLICY,
        safe_message=safe_message,
    )
    return {
        **_insufficient_decision([], safe_message),
        "step_count": state.get("step_count", 0),
        "tool_call_counts": dict(state.get("tool_call_counts", {})),
        "last_tool_error": safe_message,
        "last_error_type": AgentErrorType.POLICY,
        "last_tool_result": result.model_dump(mode="python"),
    }


def _reasoning_rejection_update(
    state: AgentState,
    safe_message: str,
) -> dict[str, object]:
    """拒绝未执行的内部 Reasoning Action，不消耗 step。"""

    return {
        **_insufficient_decision([], safe_message),
        "step_count": state.get("step_count", 0),
        "tool_call_counts": dict(state.get("tool_call_counts", {})),
        "last_tool_error": safe_message,
        "last_error_type": AgentErrorType.POLICY,
    }


def _append_action_history(
    state: AgentState,
    action: str,
    step: object,
    outcome: str,
) -> list[dict[str, object]]:
    history = list(state.get("action_history", []))
    history.append({"action": action, "step": step, "outcome": outcome})
    return history
