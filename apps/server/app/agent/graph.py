import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.context import AgentContext
from app.agent.nodes import (
    contextualize_query,
    evaluate_and_decide,
    fetch_web_page,
    generate_answer,
    generate_insufficient_answer,
    get_article_content,
    initial_decision,
    initialize,
    knowledge_search,
    non_knowledge_fast_path_check,
    rewrite_query,
    route_after_decision,
    route_after_non_knowledge_fast_path,
    route_after_rewrite,
    web_search,
)
from app.agent.state import AgentState


logger = logging.getLogger("uvicorn.error")

P = ParamSpec("P")
R = TypeVar("R")


def profile_node(
    node_name: str,
    node: Callable[P, R],
) -> Callable[P, R]:
    """记录同步 Agent Node 耗时，并保持返回值与异常语义不变。"""

    @wraps(node)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        started_at = time.perf_counter()
        outcome = "error"
        try:
            result = node(*args, **kwargs)
            outcome = "success"
            return result
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "agent_node node=%s duration_ms=%.2f outcome=%s",
                node_name,
                duration_ms,
                outcome,
            )

    return wrapped


def create_agent_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """创建由集中式 Runtime Policy 约束且全局有界的 Agent 决策图。"""

    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("initialize", initialize)
    builder.add_node(
        "non_knowledge_fast_path_check",
        profile_node(
            "non_knowledge_fast_path_check",
            non_knowledge_fast_path_check,
        ),
    )
    builder.add_node(
        "initial_decision",
        profile_node("initial_decision", initial_decision),
    )
    builder.add_node(
        "contextualize_query",
        profile_node("contextualize_query", contextualize_query),
    )
    builder.add_node(
        "knowledge_search",
        profile_node("knowledge_search", knowledge_search),
    )
    builder.add_node(
        "evaluate_and_decide",
        profile_node("evaluate_and_decide", evaluate_and_decide),
    )
    builder.add_node(
        "rewrite_query",
        profile_node("rewrite_query", rewrite_query),
    )
    builder.add_node("web_search", profile_node("web_search", web_search))
    builder.add_node(
        "get_article_content",
        profile_node("get_article_content", get_article_content),
    )
    builder.add_node(
        "fetch_web_page",
        profile_node("fetch_web_page", fetch_web_page),
    )
    builder.add_node(
        "generate_answer",
        profile_node("generate_answer", generate_answer),
    )
    builder.add_node(
        "insufficient_answer",
        profile_node("insufficient_answer", generate_insufficient_answer),
    )
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "non_knowledge_fast_path_check")
    builder.add_conditional_edges(
        "non_knowledge_fast_path_check",
        route_after_non_knowledge_fast_path,
        {
            "fast_path_answer": END,
            "main_agent": "initial_decision",
        },
    )
    builder.add_edge("initial_decision", "contextualize_query")
    builder.add_edge("contextualize_query", "knowledge_search")
    builder.add_edge("knowledge_search", "evaluate_and_decide")
    builder.add_conditional_edges(
        "evaluate_and_decide",
        route_after_decision,
        {
            "generate_answer": "generate_answer",
            "rewrite_query": "rewrite_query",
            "web_search": "web_search",
            "get_article_content": "get_article_content",
            "fetch_web_page": "fetch_web_page",
            "insufficient_answer": "insufficient_answer",
        },
    )
    builder.add_edge("web_search", "evaluate_and_decide")
    builder.add_edge("get_article_content", "evaluate_and_decide")
    builder.add_edge("fetch_web_page", "evaluate_and_decide")
    builder.add_conditional_edges(
        "rewrite_query",
        route_after_rewrite,
        {
            "knowledge_search": "knowledge_search",
            "insufficient_answer": "insufficient_answer",
        },
    )
    builder.add_edge("generate_answer", END)
    builder.add_edge("insufficient_answer", END)
    active_checkpointer = (
        checkpointer if checkpointer is not None else InMemorySaver()
    )
    return builder.compile(checkpointer=active_checkpointer)
