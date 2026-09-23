from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.graph import create_agent_graph
from app.agent.nodes import evaluate_and_decide
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentErrorType,
    AgentIntent,
    EvidenceStatus,
    IntentDecision,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
)
from app.ai.errors import LLMResponseError


class QueryKnowledgeSearchStub:
    def __init__(
        self,
        responses: dict[str, list[KnowledgeSearchResult] | Exception],
    ) -> None:
        self.responses = responses
        self.inputs: list[KnowledgeSearchInput] = []

    def search(self, payload: KnowledgeSearchInput) -> list[KnowledgeSearchResult]:
        self.inputs.append(payload)
        response = self.responses[payload.query]
        if isinstance(response, Exception):
            raise response
        return response


class NoWebSearchStub:
    def search(self, _query: str) -> list[object]:
        raise AssertionError("当前测试不应调用 Web Search")


class ScriptedReasoningStub:
    def __init__(
        self,
        *,
        decisions: list[AgentDecision | Exception] | None = None,
        contextualizations: list[str | Exception] | None = None,
        rewrites: list[str | Exception] | None = None,
        answers: list[str | Exception] | None = None,
    ) -> None:
        self.decisions = list(decisions or [])
        self.contextualizations = list(contextualizations or [])
        self.rewrites = list(rewrites or [])
        self.answers = list(answers or [])
        self.decision_inputs: list[dict[str, Any]] = []
        self.contextualize_inputs: list[dict[str, Any]] = []
        self.rewrite_inputs: list[dict[str, Any]] = []
        self.answer_inputs: list[dict[str, Any]] = []

    def classify_intent(
        self,
        **_options: object,
    ) -> IntentDecision:
        return IntentDecision(
            intent=AgentIntent.KNOWLEDGE_BASE_ONLY,
            allow_web=False,
            requires_freshness=False,
            reason="Phase 15 回归测试仅使用知识库",
        )

    def decide(
        self,
        *,
        original_query: str,
        current_query: str,
        kb_evidence: list[dict[str, Any]],
        web_evidence: list[dict[str, Any]],
        article_fulltext_evidence: list[dict[str, Any]],
        web_fulltext_evidence: list[dict[str, Any]],
        allowed_actions: list[AgentAction],
        conversation: Sequence[BaseMessage],
    ) -> AgentDecision:
        self.decision_inputs.append(
            {
                "original_query": original_query,
                "current_query": current_query,
                "kb_evidence": kb_evidence,
                "web_evidence": web_evidence,
                "article_fulltext_evidence": article_fulltext_evidence,
                "web_fulltext_evidence": web_fulltext_evidence,
                "allowed_actions": allowed_actions,
                "conversation": conversation,
            }
        )
        response = self.decisions.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def contextualize_query(
        self,
        *,
        original_query: str,
        conversation: Sequence[BaseMessage],
    ) -> str:
        self.contextualize_inputs.append(
            {
                "original_query": original_query,
                "conversation": conversation,
            }
        )
        if not self.contextualizations:
            return original_query
        response = self.contextualizations.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def rewrite_query(
        self,
        *,
        original_query: str,
        current_query: str,
        conversation: Sequence[BaseMessage],
    ) -> str:
        self.rewrite_inputs.append(
            {
                "original_query": original_query,
                "current_query": current_query,
                "conversation": conversation,
            }
        )
        response = self.rewrites.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def generate_answer(
        self,
        *,
        original_query: str,
        evidence: list[dict[str, Any]],
        evidence_status: EvidenceStatus,
        conversation: Sequence[BaseMessage],
    ) -> str:
        self.answer_inputs.append(
            {
                "original_query": original_query,
                "evidence": evidence,
                "evidence_status": evidence_status,
                "conversation": conversation,
            }
        )
        response = self.answers.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def knowledge_result(
    *,
    article_id: int = 11,
    chunk_id: int = 101,
    title: str = "Agent Memory",
    chunk_text: str = "Agent Memory 保存对话上下文。",
) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        article_id=article_id,
        chunk_id=chunk_id,
        title=title,
        chunk_text=chunk_text,
        score=0.91,
    )


def decision(
    status: EvidenceStatus,
    action: AgentAction,
    indexes: list[int] | None = None,
) -> AgentDecision:
    return AgentDecision(
        evidence_status=status,
        reason="测试决策原因",
        next_action=action,
        selected_result_indexes=indexes or [],
    )


def invoke_graph(
    question: str,
    search: QueryKnowledgeSearchStub,
    reasoning: ScriptedReasoningStub,
    *,
    graph: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_graph = graph or create_agent_graph()
    active_config = config or {"configurable": {"thread_id": str(uuid4())}}
    return active_graph.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config=active_config,
        context=AgentContext(
            knowledge_search=search,
            web_search=NoWebSearchStub(),
            reasoning=reasoning,
        ),
    )


def invoke_graph_with_messages(
    messages: list[dict[str, str]],
    search: QueryKnowledgeSearchStub,
    reasoning: ScriptedReasoningStub,
) -> dict[str, Any]:
    return create_agent_graph().invoke(
        {"messages": messages},
        config={"configurable": {"thread_id": str(uuid4())}},
        context=AgentContext(
            knowledge_search=search,
            web_search=NoWebSearchStub(),
            reasoning=reasoning,
        ),
    )


def test_sufficient_evidence_answers_without_rewrite() -> None:
    search = QueryKnowledgeSearchStub({"什么是 Agent Memory？": [knowledge_result()]})
    reasoning = ScriptedReasoningStub(
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0])],
        answers=["Agent Memory 保存对话上下文。"],
    )

    result = invoke_graph("什么是 Agent Memory？", search, reasoning)

    assert result["final_answer"] == "Agent Memory 保存对话上下文。"
    assert result["current_query"] == "什么是 Agent Memory？"
    assert result["rewrite_count"] == 0
    assert result["step_count"] == 1
    assert result["tool_call_counts"] == {"knowledge_search": 1}
    assert result["sources"] == [
        {"article_id": 11, "chunk_id": 101, "title": "Agent Memory"}
    ]
    assert reasoning.rewrite_inputs == []
    assert reasoning.contextualize_inputs == []


def test_follow_up_query_is_contextualized_before_first_search() -> None:
    contextualized = "大语言模型训练的第二阶段有监督微调 SFT 主要做了什么？"
    result_item = knowledge_result(
        chunk_text="第二阶段通过有监督微调学习遵循指令。"
    )
    search = QueryKnowledgeSearchStub({contextualized: [result_item]})
    reasoning = ScriptedReasoningStub(
        contextualizations=[contextualized],
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0])],
        answers=["第二阶段主要进行有监督微调。"],
    )

    result = invoke_graph_with_messages(
        [
            {"role": "user", "content": "大语言模型怎么训练的？"},
            {
                "role": "assistant",
                "content": "第二阶段是有监督微调 SFT。",
            },
            {"role": "user", "content": "那第二阶段主要做了什么？"},
        ],
        search,
        reasoning,
    )

    assert result["original_query"] == "那第二阶段主要做了什么？"
    assert result["current_query"] == contextualized
    assert [item.query for item in search.inputs] == [contextualized]
    assert result["rewrite_count"] == 0
    assert result["step_count"] == 1
    assert result["kb_results"] == [result_item.model_dump(mode="json")]
    assert result["article_fulltext_evidence"] == []
    assert result["selected_evidence"] == [
        {
            "source_type": "knowledge_base",
            **result_item.model_dump(mode="json"),
        }
    ]


def test_complete_follow_up_query_may_remain_unchanged() -> None:
    query = "RAG 和 Fine-tuning 有什么区别？"
    search = QueryKnowledgeSearchStub({query: []})
    reasoning = ScriptedReasoningStub(
        contextualizations=[query],
        decisions=[decision(EvidenceStatus.INSUFFICIENT, AgentAction.INSUFFICIENT)],
    )

    result = invoke_graph_with_messages(
        [
            {"role": "user", "content": "先聊聊模型训练。"},
            {"role": "assistant", "content": "可以。"},
            {"role": "user", "content": query},
        ],
        search,
        reasoning,
    )

    assert result["current_query"] == query
    assert [item.query for item in search.inputs] == [query]
    assert len(reasoning.contextualize_inputs) == 1


def test_contextualization_failure_falls_back_and_continues_search(
    caplog: Any,
) -> None:
    query = "那第二阶段主要做了什么？"
    result_item = knowledge_result()
    search = QueryKnowledgeSearchStub({query: [result_item]})
    reasoning = ScriptedReasoningStub(
        contextualizations=[LLMResponseError("敏感 Provider 详情")],
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0])],
        answers=["基于原始问题检索后生成的回答。"],
    )

    result = invoke_graph_with_messages(
        [
            {"role": "user", "content": "大语言模型怎么训练的？"},
            {"role": "assistant", "content": "可以分成多个阶段。"},
            {"role": "user", "content": query},
        ],
        search,
        reasoning,
    )

    assert result["current_query"] == query
    assert [item.query for item in search.inputs] == [query]
    assert result["final_answer"] == "基于原始问题检索后生成的回答。"
    assert result["last_error_type"] is None
    assert len(reasoning.contextualize_inputs) == 1
    assert "LLMResponseError" in caplog.text
    assert "敏感 Provider 详情" not in caplog.text


def test_contextualization_preserves_retrieval_retry_budget() -> None:
    contextualized = "大语言模型训练的第二阶段主要做了什么？"
    retry_query = "大语言模型 第二阶段 SFT 训练目标"
    result_item = knowledge_result()
    search = QueryKnowledgeSearchStub(
        {
            contextualized: [],
            retry_query: [result_item],
        }
    )
    reasoning = ScriptedReasoningStub(
        contextualizations=[contextualized],
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.REWRITE_QUERY),
            decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0]),
        ],
        rewrites=[retry_query],
        answers=["第二阶段的目标。"],
    )

    result = invoke_graph_with_messages(
        [
            {"role": "user", "content": "大语言模型怎么训练的？"},
            {"role": "assistant", "content": "训练包含多个阶段。"},
            {"role": "user", "content": "那第二阶段主要做了什么？"},
        ],
        search,
        reasoning,
    )

    assert [item.query for item in search.inputs] == [contextualized, retry_query]
    assert result["rewrite_count"] == 1
    assert result["tool_call_counts"] == {"knowledge_search": 2}
    assert result["final_answer"] == "第二阶段的目标。"


def test_graph_routes_contextualization_before_knowledge_search() -> None:
    edges = {
        (edge.source, edge.target)
        for edge in create_agent_graph().get_graph().edges
    }

    assert ("initial_decision", "contextualize_query") in edges
    assert ("contextualize_query", "knowledge_search") in edges
    assert ("initial_decision", "knowledge_search") not in edges


def test_insufficient_first_search_rewrites_once_then_answers() -> None:
    search = QueryKnowledgeSearchStub(
        {
            "记忆是什么？": [],
            "Agent Memory 对话上下文": [knowledge_result()],
        }
    )
    reasoning = ScriptedReasoningStub(
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.REWRITE_QUERY),
            decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0]),
        ],
        rewrites=["Agent Memory 对话上下文"],
        answers=["Agent Memory 保存对话上下文。"],
    )

    result = invoke_graph("记忆是什么？", search, reasoning)

    assert result["original_query"] == "记忆是什么？"
    assert result["current_query"] == "Agent Memory 对话上下文"
    assert result["rewrite_count"] == 1
    assert result["step_count"] == 3
    assert result["tool_call_counts"] == {"knowledge_search": 2}
    assert [item.query for item in search.inputs] == [
        "记忆是什么？",
        "Agent Memory 对话上下文",
    ]
    assert result["final_answer"] == "Agent Memory 保存对话上下文。"


def test_empty_second_search_terminates_without_factual_answer() -> None:
    query = "不要联网，只根据知识库回答未知主题"
    search = QueryKnowledgeSearchStub({query: [], "更精确的未知主题": []})
    reasoning = ScriptedReasoningStub(
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.REWRITE_QUERY)
        ],
        rewrites=["更精确的未知主题"],
    )

    result = invoke_graph(query, search, reasoning)

    assert result["rewrite_count"] == 1
    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT
    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert "无法" in result["final_answer"]
    assert reasoning.answers == []
    assert len(reasoning.decision_inputs) == 1


def test_knowledge_search_timeout_terminates_without_decision_loop() -> None:
    search = QueryKnowledgeSearchStub({"超时问题": TimeoutError("敏感详情")})
    reasoning = ScriptedReasoningStub()

    result = invoke_graph("超时问题", search, reasoning)

    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT
    assert result["rewrite_count"] == 0
    assert result["last_tool_error"] == "Knowledge Search 执行失败（TimeoutError）"
    assert result["last_error_type"] is AgentErrorType.EXECUTION
    assert "敏感详情" not in result["final_answer"]
    assert reasoning.decision_inputs == []


def test_rewrite_is_rejected_after_budget_is_exhausted() -> None:
    search = QueryKnowledgeSearchStub(
        {"初始问题": [], "改写问题": [knowledge_result()]}
    )
    reasoning = ScriptedReasoningStub(
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.REWRITE_QUERY),
            decision(EvidenceStatus.PARTIAL, AgentAction.REWRITE_QUERY),
        ],
        rewrites=["改写问题"],
    )

    result = invoke_graph("初始问题", search, reasoning)

    assert result["rewrite_count"] == 1
    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert AgentAction.REWRITE_QUERY not in result["allowed_actions"]
    assert result["last_error_type"] is AgentErrorType.REASONING
    assert len(search.inputs) == 2
    assert "无法" in result["final_answer"]


def test_malformed_decision_output_fails_safely() -> None:
    search = QueryKnowledgeSearchStub({"问题": [knowledge_result()]})
    reasoning = ScriptedReasoningStub(
        decisions=[LLMResponseError("LLM 返回的 Agent 决策结果无效")]
    )

    result = invoke_graph("问题", search, reasoning)

    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert result["last_tool_error"] == "Agent 决策失败（LLMResponseError）"
    assert result["last_error_type"] is AgentErrorType.REASONING
    assert "无法" in result["final_answer"]


def test_rewrite_failure_terminates_without_retry_or_detail_leak() -> None:
    search = QueryKnowledgeSearchStub({"问题": []})
    reasoning = ScriptedReasoningStub(
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.REWRITE_QUERY)
        ],
        rewrites=[RuntimeError("敏感改写详情")],
    )

    result = invoke_graph("问题", search, reasoning)

    assert result["rewrite_count"] == 1
    assert result["step_count"] == 2
    assert result["tool_call_counts"] == {"knowledge_search": 1}
    assert result["last_tool_error"] == "Query Rewrite 执行失败（RuntimeError）"
    assert result["last_error_type"] is AgentErrorType.REASONING
    assert "敏感改写详情" not in result["final_answer"]
    assert len(search.inputs) == 1


def test_answer_failure_returns_no_sources_or_detail_leak() -> None:
    search = QueryKnowledgeSearchStub({"问题": [knowledge_result()]})
    reasoning = ScriptedReasoningStub(
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0])],
        answers=[RuntimeError("敏感回答详情")],
    )

    result = invoke_graph("问题", search, reasoning)

    assert result["last_tool_error"] == "Agent 回答生成失败（RuntimeError）"
    assert result["last_error_type"] is AgentErrorType.REASONING
    assert result["sources"] == []
    assert "敏感回答详情" not in result["final_answer"]
    assert len(search.inputs) == 1


def test_partial_answer_uses_only_selected_evidence_and_states_gap() -> None:
    selected = knowledge_result()
    unselected = knowledge_result(
        article_id=12,
        chunk_id=202,
        title="未选文章",
        chunk_text="不应进入回答的内容。",
    )
    search = QueryKnowledgeSearchStub({"复合问题": [selected, unselected]})
    reasoning = ScriptedReasoningStub(
        decisions=[decision(EvidenceStatus.PARTIAL, AgentAction.ANSWER, [0])],
        answers=["知识库仅说明 Agent Memory 保存对话上下文。"],
    )

    result = invoke_graph("复合问题", search, reasoning)

    assert "其余内容无法根据当前知识库确认" in result["final_answer"]
    assert reasoning.answer_inputs[0]["evidence"] == [
        {
            "source_type": "knowledge_base",
            **selected.model_dump(mode="json"),
        }
    ]
    assert result["sources"] == [
        {"article_id": 11, "chunk_id": 101, "title": "Agent Memory"}
    ]


def test_invalid_selected_index_cannot_generate_answer() -> None:
    search = QueryKnowledgeSearchStub({"问题": [knowledge_result()]})
    reasoning = ScriptedReasoningStub(
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [5])]
    )

    result = invoke_graph("问题", search, reasoning)

    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert result["selected_evidence"] == []
    assert reasoning.answer_inputs == []


def test_empty_web_candidates_reject_selected_web_index_with_range_log(
    caplog,
) -> None:
    search = QueryKnowledgeSearchStub({"问题": [knowledge_result()]})
    reasoning = ScriptedReasoningStub(
        decisions=[
            AgentDecision(
                evidence_status=EvidenceStatus.SUFFICIENT,
                reason="错误选择不存在的网页证据",
                next_action=AgentAction.ANSWER,
                selected_web_result_indexes=[0],
            )
        ]
    )

    result = invoke_graph("问题", search, reasoning)

    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert "field=selected_web_result_indexes" in caplog.text
    assert "indexes=[0]" in caplog.text
    assert "candidate_count=0" in caplog.text
    assert "valid_indexes=[]" in caplog.text


def test_out_of_range_web_index_is_rejected_with_dynamic_range_log(
    caplog,
) -> None:
    state: dict[str, Any] = {
        "original_query": "问题",
        "current_query": "问题",
        "messages": [HumanMessage(content="问题")],
        "allow_web": True,
        "requires_freshness": False,
        "kb_results": [],
        "web_results": [
            {
                "title": "网页证据",
                "url": "https://example.com/current",
                "snippet": "网页摘要",
                "source": "example.com",
                "published_at": None,
            }
        ],
        "article_fulltext_evidence": [],
        "web_fulltext_evidence": [],
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.UNKNOWN,
        "rewrite_count": 0,
        "step_count": 0,
        "tool_call_counts": {"web_search": 1},
        "read_article_ids": [],
        "fetched_web_urls": [],
        "last_error_type": None,
    }
    reasoning = ScriptedReasoningStub(
        decisions=[
            AgentDecision(
                evidence_status=EvidenceStatus.SUFFICIENT,
                reason="错误选择越界网页证据",
                next_action=AgentAction.ANSWER,
                selected_web_result_indexes=[1],
            )
        ]
    )
    runtime = Runtime(
        context=AgentContext(
            knowledge_search=QueryKnowledgeSearchStub({}),
            web_search=NoWebSearchStub(),
            reasoning=reasoning,
        )
    )

    update = evaluate_and_decide(state, runtime)  # type: ignore[arg-type]

    assert update["next_action"] is AgentAction.INSUFFICIENT
    assert "field=selected_web_result_indexes" in caplog.text
    assert "indexes=[1]" in caplog.text
    assert "candidate_count=1" in caplog.text
    assert "valid_indexes=[0]" in caplog.text


def test_decision_selection_uses_the_same_candidate_snapshot() -> None:
    web_candidate = {
        "title": "网页证据",
        "url": "https://example.com/current",
        "snippet": "网页摘要",
        "source": "example.com",
        "published_at": None,
    }
    web_results = [web_candidate]
    state: dict[str, Any] = {
        "original_query": "问题",
        "current_query": "问题",
        "messages": [HumanMessage(content="问题")],
        "allow_web": True,
        "requires_freshness": False,
        "kb_results": [],
        "web_results": web_results,
        "article_fulltext_evidence": [],
        "web_fulltext_evidence": [],
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.UNKNOWN,
        "rewrite_count": 0,
        "step_count": 0,
        "tool_call_counts": {"web_search": 1},
        "read_article_ids": [],
        "fetched_web_urls": [],
        "last_error_type": None,
    }

    class MutatingReasoningStub(ScriptedReasoningStub):
        def decide(self, **options: Any) -> AgentDecision:
            result = super().decide(**options)
            web_results.clear()
            return result

    reasoning = MutatingReasoningStub(
        decisions=[
            AgentDecision(
                evidence_status=EvidenceStatus.SUFFICIENT,
                reason="选择快照中的网页证据",
                next_action=AgentAction.ANSWER,
                selected_web_result_indexes=[0],
            )
        ]
    )
    runtime = Runtime(
        context=AgentContext(
            knowledge_search=QueryKnowledgeSearchStub({}),
            web_search=NoWebSearchStub(),
            reasoning=reasoning,
        )
    )

    update = evaluate_and_decide(state, runtime)  # type: ignore[arg-type]

    assert update["next_action"] is AgentAction.ANSWER
    assert update["selected_evidence"] == [
        {"source_type": "web", **web_candidate}
    ]


def test_same_thread_preserves_messages_but_resets_run_state() -> None:
    graph = create_agent_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}
    first_search = QueryKnowledgeSearchStub({"第一问": [knowledge_result()]})
    first_reasoning = ScriptedReasoningStub(
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0])],
        answers=["第一答"],
    )
    invoke_graph(
        "第一问",
        first_search,
        first_reasoning,
        graph=graph,
        config=config,
    )
    second_result = knowledge_result(
        article_id=22,
        chunk_id=202,
        title="第二篇",
        chunk_text="第二问的证据。",
    )
    second_search = QueryKnowledgeSearchStub({"第二问": [second_result]})
    second_reasoning = ScriptedReasoningStub(
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, [0])],
        answers=["第二答"],
    )

    result = invoke_graph(
        "第二问",
        second_search,
        second_reasoning,
        graph=graph,
        config=config,
    )

    assert result["original_query"] == "第二问"
    assert result["current_query"] == "第二问"
    assert result["rewrite_count"] == 0
    assert result["step_count"] == 1
    assert result["tool_call_counts"] == {"knowledge_search": 1}
    assert result["kb_results"] == [second_result.model_dump(mode="json")]
    assert [message.content for message in result["messages"]] == [
        "第一问",
        "第一答",
        "第二问",
        "第二答",
    ]
