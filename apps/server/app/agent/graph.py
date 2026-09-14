from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.context import AgentContext
from app.agent.nodes import (
    evaluate_and_decide,
    fetch_web_page,
    generate_answer,
    generate_insufficient_answer,
    get_article_content,
    initial_decision,
    initialize,
    knowledge_search,
    rewrite_query,
    route_after_decision,
    route_after_rewrite,
    web_search,
)
from app.agent.state import AgentState


def create_agent_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """创建由集中式 Runtime Policy 约束且全局有界的 Agent 决策图。"""

    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("initialize", initialize)
    builder.add_node("initial_decision", initial_decision)
    builder.add_node("knowledge_search", knowledge_search)
    builder.add_node("evaluate_and_decide", evaluate_and_decide)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("web_search", web_search)
    builder.add_node("get_article_content", get_article_content)
    builder.add_node("fetch_web_page", fetch_web_page)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("insufficient_answer", generate_insufficient_answer)
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "initial_decision")
    builder.add_edge("initial_decision", "knowledge_search")
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
