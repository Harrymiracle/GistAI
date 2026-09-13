from typing import Any
from uuid import uuid4

import pytest
from langgraph.runtime import Runtime
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.context import AgentContext
from app.agent.graph import create_agent_graph
from app.agent.knowledge_search import KnowledgeSearchService
from app.agent.nodes import knowledge_search
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    EvidenceStatus,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
)
from app.services.search import SearchService, SemanticSearchHit


class KnowledgeSearchStub:
    def __init__(
        self,
        results: list[KnowledgeSearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.inputs: list[KnowledgeSearchInput] = []

    def search(self, payload: KnowledgeSearchInput) -> list[KnowledgeSearchResult]:
        self.inputs.append(payload)
        if self.error is not None:
            raise self.error
        return self.results


class QueryEmbeddingStub:
    def embed_query(self, _query: str) -> list[float]:
        return [0.0] * 1024


class InsufficientReasoningStub:
    def decide(self, **_options: object) -> AgentDecision:
        return AgentDecision(
            evidence_status=EvidenceStatus.INSUFFICIENT,
            reason="测试选择安全终止",
            next_action=AgentAction.INSUFFICIENT,
        )

    def rewrite_query(self, **_options: object) -> str:
        raise AssertionError("不应改写查询")

    def generate_answer(self, **_options: object) -> str:
        raise AssertionError("不应生成回答")


def knowledge_result() -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        article_id=11,
        chunk_id=101,
        title="Agent Memory",
        chunk_text="Agent memory keeps conversation context.",
        score=0.91,
    )


def runtime_for(
    search: KnowledgeSearchStub,
    *,
    top_k: int = 5,
) -> Runtime[AgentContext]:
    return Runtime(
        context=AgentContext(
            knowledge_search=search,
            reasoning=InsufficientReasoningStub(),
            top_k=top_k,
        )
    )


def test_knowledge_search_input_validates_query_and_top_k() -> None:
    payload = KnowledgeSearchInput(query="  Agent Memory  ", top_k=10)

    assert payload.query == "Agent Memory"
    assert payload.top_k == 10

    for invalid_top_k in (0, 11):
        with pytest.raises(ValidationError):
            KnowledgeSearchInput(query="Agent Memory", top_k=invalid_top_k)

    with pytest.raises(ValidationError):
        KnowledgeSearchInput(query="   ", top_k=5)


def test_service_reuses_semantic_search_and_maps_structured_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    hit = SemanticSearchHit(
        article_id=11,
        title="Agent Memory",
        chunk_id=101,
        chunk_index=2,
        excerpt="Agent memory keeps conversation context.",
        score=0.91,
        one_sentence_summary="Agent memory overview.",
        source_url="https://example.com/agent-memory",
        source_name="Example",
    )

    def semantic_search(
        session: Session,
        user_id: int,
        query: str,
        **options: Any,
    ) -> list[SemanticSearchHit]:
        captured.update(
            session=session,
            user_id=user_id,
            query=query,
            **options,
        )
        return [hit]

    monkeypatch.setattr(SearchService, "semantic_search", semantic_search)
    with Session() as session:
        embedding_service = QueryEmbeddingStub()
        service = KnowledgeSearchService(
            session=session,
            user_id=7,
            embedding_service=embedding_service,
            similarity_threshold=0.35,
        )

        results = service.search(KnowledgeSearchInput(query="Agent Memory", top_k=4))

    assert results == [knowledge_result()]
    assert captured == {
        "session": session,
        "user_id": 7,
        "query": "Agent Memory",
        "top_k": 4,
        "similarity_threshold": 0.35,
        "embedding_service": embedding_service,
    }


def test_knowledge_search_node_writes_results_and_increments_counters() -> None:
    search = KnowledgeSearchStub([knowledge_result()])

    update = knowledge_search(
        {
            "current_query": "Agent Memory",
            "step_count": 2,
            "tool_call_counts": {"knowledge_search": 1},
        },
        runtime_for(search, top_k=4),
    )

    assert search.inputs == [KnowledgeSearchInput(query="Agent Memory", top_k=4)]
    assert update["kb_results"] == [
        {
            "article_id": 11,
            "chunk_id": 101,
            "title": "Agent Memory",
            "chunk_text": "Agent memory keeps conversation context.",
            "score": 0.91,
        }
    ]
    assert update["step_count"] == 3
    assert update["tool_call_counts"] == {"knowledge_search": 2}
    assert update["last_tool_error"] is None


def test_empty_result_is_success_without_tool_error() -> None:
    update = knowledge_search(
        {"current_query": "Unknown topic", "step_count": 0, "tool_call_counts": {}},
        runtime_for(KnowledgeSearchStub()),
    )

    assert update["kb_results"] == []
    assert update["step_count"] == 1
    assert update["tool_call_counts"] == {"knowledge_search": 1}
    assert update["last_tool_error"] is None


def test_execution_error_is_recorded_without_leaking_details() -> None:
    update = knowledge_search(
        {
            "current_query": "Agent Memory",
            "kb_results": [{"chunk_id": 999, "chunk_text": "旧候选证据"}],
            "step_count": 0,
            "tool_call_counts": {},
        },
        runtime_for(
            KnowledgeSearchStub(error=TimeoutError("sensitive connection detail"))
        ),
    )

    assert update["kb_results"] == []
    assert update["step_count"] == 1
    assert update["tool_call_counts"] == {"knowledge_search": 1}
    assert update["last_tool_error"] == "Knowledge Search 执行失败（TimeoutError）"
    assert "sensitive connection detail" not in update["last_tool_error"]


def test_graph_runs_knowledge_search_and_keeps_checkpoint() -> None:
    search = KnowledgeSearchStub([knowledge_result()])
    graph = create_agent_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}
    context = AgentContext(
        knowledge_search=search,
        reasoning=InsufficientReasoningStub(),
        top_k=3,
    )

    result = graph.invoke(
        {"messages": [{"role": "user", "content": "Agent Memory"}]},
        config=config,
        context=context,
    )

    checkpoint = graph.get_state(config)
    assert search.inputs == [KnowledgeSearchInput(query="Agent Memory", top_k=3)]
    assert result["kb_results"][0]["chunk_id"] == 101
    assert result["step_count"] == 1
    assert "无法" in result["final_answer"]
    assert checkpoint.values["kb_results"] == result["kb_results"]
