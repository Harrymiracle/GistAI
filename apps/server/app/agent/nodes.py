from collections.abc import Sequence
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentIntent,
    EvidenceStatus,
    KnowledgeSearchInput,
)
from app.agent.state import AgentState
from app.agent.web_page_fetch import WebPageValidationError


MAX_REWRITES = 1
MAX_WEB_SEARCHES = 1
MAX_ARTICLE_READS = 2
MAX_WEB_PAGE_READS = 2
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
            "证据工具执行失败，无法继续评估。",
        )
    if allowed_actions == [AgentAction.INSUFFICIENT]:
        return _insufficient_decision(
            allowed_actions,
            "所有受控动作均已用尽，仍未找到可用证据。",
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
        "selected_article_result_index": decision.selected_article_result_index,
        "selected_web_page_result_index": decision.selected_web_page_result_index,
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


def web_search(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """在单轮一次的硬预算内获取搜索结果摘要。"""

    web_search_count = state.get("tool_call_counts", {}).get("web_search", 0)
    if not state.get("allow_web") or web_search_count >= MAX_WEB_SEARCHES:
        return {
            **_insufficient_decision(
                [AgentAction.INSUFFICIENT],
                "Web Search 未获授权或已达到调用上限。",
            ),
            "last_tool_error": "Web Search 被程序限制拒绝",
        }

    tool_call_counts = dict(state.get("tool_call_counts", {}))
    tool_call_counts["web_search"] = web_search_count + 1
    update: dict[str, object] = {
        "step_count": state.get("step_count", 0) + 1,
        "tool_call_counts": tool_call_counts,
    }
    try:
        results = runtime.context.web_search.search(state["current_query"])
    except Exception as exc:
        update.update(
            web_results=[],
            last_tool_error=f"Web Search 执行失败（{type(exc).__name__}）",
        )
        return update

    update.update(
        web_results=[result.model_dump(mode="json") for result in results],
        selected_evidence=[],
        evidence_status=EvidenceStatus.UNKNOWN,
        evidence_reason=None,
        next_action=None,
        last_tool_error=None,
    )
    return update


def get_article_content(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """读取候选知识库文章全文，并只保留有界的相关上下文。"""

    count = state.get("tool_call_counts", {}).get("get_article_content", 0)
    index = state.get("selected_article_result_index")
    candidates = list(state.get("kb_results", []))
    read_ids = list(state.get("read_article_ids", []))
    if count >= MAX_ARTICLE_READS or index is None or index >= len(candidates):
        return _rejected_tool_update("Article Read 未获授权或已达到调用上限。")

    article_id = candidates[index]["article_id"]
    if not isinstance(article_id, int) or article_id in read_ids:
        return _rejected_tool_update("Article Read 候选无效或已读取。")
    if (
        runtime.context.article_content is None
        or runtime.context.fulltext_selector is None
    ):
        return _rejected_tool_update("Article Read 运行时依赖不可用。")

    tool_call_counts = dict(state.get("tool_call_counts", {}))
    tool_call_counts["get_article_content"] = count + 1
    update: dict[str, object] = {
        "step_count": state.get("step_count", 0) + 1,
        "tool_call_counts": tool_call_counts,
        "read_article_ids": [*read_ids, article_id],
        "selected_article_result_index": None,
    }
    try:
        result = runtime.context.article_content.get(article_id)
    except Exception as exc:
        update.update(
            last_tool_error=(
                f"Article Content 执行失败（{type(exc).__name__}）"
            )
        )
        return update

    article_contents = list(state.get("article_contents", []))
    if result is not None:
        article_contents.append(result.model_dump(mode="json"))
    article_evidence, web_evidence = runtime.context.fulltext_selector.select(
        query=state["current_query"],
        article_contents=article_contents,
        web_page_contents=list(state.get("web_page_contents", [])),
    )
    update.update(
        article_contents=article_contents,
        article_fulltext_evidence=article_evidence,
        web_fulltext_evidence=web_evidence,
        selected_evidence=[],
        evidence_status=EvidenceStatus.UNKNOWN,
        evidence_reason=(
            None if result is not None else "候选文章不存在或当前不可用。"
        ),
        next_action=None,
        last_tool_error=None,
    )
    return update


def fetch_web_page(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, object]:
    """抓取已搜索 URL 的全文，并只保留有界的相关上下文。"""

    count = state.get("tool_call_counts", {}).get("fetch_web_page", 0)
    index = state.get("selected_web_page_result_index")
    candidates = list(state.get("web_results", []))
    fetched_urls = list(state.get("fetched_web_urls", []))
    if count >= MAX_WEB_PAGE_READS or index is None or index >= len(candidates):
        return _rejected_tool_update("Web Page Fetch 未获授权或已达到调用上限。")

    url = str(candidates[index]["url"])
    if url in fetched_urls:
        return _rejected_tool_update("Web Page Fetch 候选无效或已读取。")
    if (
        runtime.context.web_page_fetch is None
        or runtime.context.fulltext_selector is None
    ):
        return _rejected_tool_update("Web Page Fetch 运行时依赖不可用。")

    try:
        result = runtime.context.web_page_fetch.fetch(url)
    except WebPageValidationError:
        return _rejected_tool_update("Web Page Fetch 地址未通过安全校验。")
    except Exception as exc:
        tool_call_counts = dict(state.get("tool_call_counts", {}))
        tool_call_counts["fetch_web_page"] = count + 1
        return {
            "step_count": state.get("step_count", 0) + 1,
            "tool_call_counts": tool_call_counts,
            "fetched_web_urls": [*fetched_urls, url],
            "selected_web_page_result_index": None,
            "last_tool_error": f"Web Page Fetch 执行失败（{type(exc).__name__}）",
        }

    tool_call_counts = dict(state.get("tool_call_counts", {}))
    tool_call_counts["fetch_web_page"] = count + 1
    web_page = result.model_dump(mode="json")
    web_page["title"] = result.title or candidates[index].get("title")
    web_page["source"] = result.source or candidates[index].get("source")
    web_page["published_at"] = (
        web_page.get("published_at") or candidates[index].get("published_at")
    )
    web_page_contents = [
        *list(state.get("web_page_contents", [])),
        web_page,
    ]
    article_evidence, web_evidence = runtime.context.fulltext_selector.select(
        query=state["current_query"],
        article_contents=list(state.get("article_contents", [])),
        web_page_contents=web_page_contents,
    )
    return {
        "step_count": state.get("step_count", 0) + 1,
        "tool_call_counts": tool_call_counts,
        "fetched_web_urls": [*fetched_urls, url],
        "web_page_contents": web_page_contents,
        "article_fulltext_evidence": article_evidence,
        "web_fulltext_evidence": web_evidence,
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.UNKNOWN,
        "evidence_reason": None,
        "next_action": None,
        "selected_web_page_result_index": None,
        "last_tool_error": None,
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
        )

    if state["evidence_status"] is EvidenceStatus.PARTIAL:
        answer = f"{answer}\n\n{PARTIAL_GAP_NOTICE}"
    sources = [_source_from_evidence(item) for item in selected_evidence]
    return _answer_update(answer, sources, None)


def generate_insufficient_answer(state: AgentState) -> dict[str, object]:
    """以确定性模板结束无可靠证据或依赖失败的运行。"""

    answer = FAILED_ANSWER if state.get("last_tool_error") else INSUFFICIENT_ANSWER
    return _answer_update(answer, [], state.get("last_tool_error"))


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

    if state.get("next_action") is AgentAction.ANSWER:
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


def _allowed_actions(state: AgentState) -> list[AgentAction]:
    if state.get("last_tool_error"):
        return [AgentAction.INSUFFICIENT]
    has_evidence = bool(
        state.get("kb_results")
        or state.get("web_results")
        or state.get("article_fulltext_evidence")
        or state.get("web_fulltext_evidence")
    )
    can_rewrite = state.get("rewrite_count", 0) < MAX_REWRITES
    web_search_count = state.get("tool_call_counts", {}).get("web_search", 0)
    can_search_web = (
        state.get("allow_web", False)
        and web_search_count < MAX_WEB_SEARCHES
    )
    freshness_verified = (
        not state.get("requires_freshness", False)
        or bool(state.get("web_results"))
    )
    actions: list[AgentAction] = []
    if has_evidence and freshness_verified:
        actions.append(AgentAction.ANSWER)
    if can_rewrite:
        actions.append(AgentAction.REWRITE_QUERY)
    if can_search_web:
        actions.append(AgentAction.WEB_SEARCH)
    read_article_ids = set(state.get("read_article_ids", []))
    unread_articles = {
        item.get("article_id") for item in state.get("kb_results", [])
    } - read_article_ids
    if (
        unread_articles
        and state.get("tool_call_counts", {}).get("get_article_content", 0)
        < MAX_ARTICLE_READS
    ):
        actions.append(AgentAction.GET_ARTICLE_CONTENT)
    fetched_urls = set(state.get("fetched_web_urls", []))
    unfetched_urls = {
        str(item.get("url")) for item in state.get("web_results", [])
    } - fetched_urls
    if (
        unfetched_urls
        and state.get("tool_call_counts", {}).get("fetch_web_page", 0)
        < MAX_WEB_PAGE_READS
    ):
        actions.append(AgentAction.FETCH_WEB_PAGE)
    actions.append(AgentAction.INSUFFICIENT)
    return actions


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


def _rejected_tool_update(reason: str) -> dict[str, object]:
    return {
        **_insufficient_decision([AgentAction.INSUFFICIENT], reason),
        "last_tool_error": "全文读取请求被程序限制拒绝",
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
