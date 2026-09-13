from uuid import uuid4

from langchain_core.messages import HumanMessage

from app.agent.context import AgentContext
from app.agent.graph import create_agent_graph
from app.agent.nodes import initialize
from app.agent.schemas import (
    EvidenceStatus,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
)


class EmptyKnowledgeSearchStub:
    def search(
        self,
        _payload: KnowledgeSearchInput,
    ) -> list[KnowledgeSearchResult]:
        return []


def empty_search_context() -> AgentContext:
    return AgentContext(knowledge_search=EmptyKnowledgeSearchStub())


def test_agent_graph_runs_to_end_with_placeholder_answer() -> None:
    graph = create_agent_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}

    result = graph.invoke(
        {"messages": [{"role": "user", "content": "What is Agent Memory?"}]},
        config=config,
        context=empty_search_context(),
    )

    assert result["final_answer"] == "Agent graph initialized successfully."


def test_initialize_sets_queries_and_control_defaults() -> None:
    result = initialize(
        {"messages": [HumanMessage(content="What is Agent Memory?")]}
    )

    assert result["original_query"] == "What is Agent Memory?"
    assert result["current_query"] == "What is Agent Memory?"
    assert result["intent"] is None
    assert result["allow_web"] is False
    assert result["requires_freshness"] is False
    assert result["kb_results"] == []
    assert result["web_results"] == []
    assert result["article_contents"] == []
    assert result["web_page_contents"] == []
    assert result["selected_evidence"] == []
    assert result["evidence_status"] is EvidenceStatus.UNKNOWN
    assert result["evidence_reason"] is None
    assert result["rewrite_count"] == 0
    assert result["step_count"] == 0
    assert result["tool_call_counts"] == {}
    assert result["allowed_actions"] == []
    assert result["next_action"] is None
    assert result["last_tool_error"] is None
    assert result["sources"] == []


def test_same_thread_uses_checkpoint_and_preserves_original_query() -> None:
    graph = create_agent_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}

    graph.invoke(
        {"messages": [{"role": "user", "content": "First question"}]},
        config=config,
        context=empty_search_context(),
    )
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "Follow-up question"}]},
        config=config,
        context=empty_search_context(),
    )
    checkpoint = graph.get_state(config)

    assert result["original_query"] == "First question"
    assert result["current_query"] == "Follow-up question"
    assert len(result["messages"]) == 2
    assert result["step_count"] == 2
    assert result["tool_call_counts"]["knowledge_search"] == 2
    assert checkpoint.values["final_answer"] == result["final_answer"]
    assert checkpoint.values["current_query"] == "Follow-up question"
    assert checkpoint.values["step_count"] == 2
    assert checkpoint.values["tool_call_counts"]["knowledge_search"] == 2
