import logging
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from langchain_core.messages import BaseMessage

from app.agent.context import AgentContext
from app.agent.graph import create_agent_graph
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentErrorType,
    AgentIntent,
    EvidenceStatus,
    IntentDecision,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
    WebSearchResult,
)


class KnowledgeSearchStub:
    def __init__(self, responses: dict[str, list[KnowledgeSearchResult]]) -> None:
        self.responses = responses
        self.inputs: list[KnowledgeSearchInput] = []

    def search(self, payload: KnowledgeSearchInput) -> list[KnowledgeSearchResult]:
        self.inputs.append(payload)
        return self.responses[payload.query]


class WebSearchStub:
    def __init__(
        self,
        responses: list[list[WebSearchResult] | Exception],
    ) -> None:
        self.responses = list(responses)
        self.queries: list[str] = []

    def search(self, query: str) -> list[WebSearchResult]:
        self.queries.append(query)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ReasoningStub:
    def __init__(
        self,
        *,
        intent: IntentDecision,
        decisions: list[AgentDecision],
        answers: list[str] | None = None,
    ) -> None:
        self.intent = intent
        self.decisions = list(decisions)
        self.answers = list(answers or [])
        self.decision_inputs: list[dict[str, Any]] = []
        self.answer_inputs: list[dict[str, Any]] = []

    def classify_intent(
        self,
        *,
        query: str,
        conversation: Sequence[BaseMessage],
    ) -> IntentDecision:
        return self.intent

    def decide(self, **options: Any) -> AgentDecision:
        self.decision_inputs.append(options)
        return self.decisions.pop(0)

    def rewrite_query(self, **_options: Any) -> str:
        raise AssertionError("当前测试不应改写查询")

    def generate_answer(self, **options: Any) -> str:
        self.answer_inputs.append(options)
        return self.answers.pop(0)


def intent(
    value: AgentIntent,
    *,
    allow_web: bool,
    requires_freshness: bool = False,
) -> IntentDecision:
    return IntentDecision(
        intent=value,
        allow_web=allow_web,
        requires_freshness=requires_freshness,
        reason="测试意图",
    )


def decision(
    status: EvidenceStatus,
    action: AgentAction,
    *,
    kb: list[int] | None = None,
    web: list[int] | None = None,
) -> AgentDecision:
    return AgentDecision(
        evidence_status=status,
        reason="测试决策",
        next_action=action,
        selected_result_indexes=kb or [],
        selected_web_result_indexes=web or [],
    )


def kb_result() -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        article_id=11,
        chunk_id=101,
        title="知识库文章",
        chunk_text="知识库中的稳定事实。",
        score=0.91,
    )


def web_result(
    *,
    title: str = "官方更新",
    snippet: str = "当前版本是 2.0。",
) -> WebSearchResult:
    return WebSearchResult(
        title=title,
        url="https://example.com/update",
        snippet=snippet,
        source="example.com",
        published_at="2026-09-14",
    )


def run(
    question: str,
    *,
    knowledge: KnowledgeSearchStub,
    web: WebSearchStub,
    reasoning: ReasoningStub,
    graph: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return (graph or create_agent_graph()).invoke(
        {"messages": [{"role": "user", "content": question}]},
        config=config or {"configurable": {"thread_id": str(uuid4())}},
        context=AgentContext(
            knowledge_search=knowledge,
            web_search=web,
            reasoning=reasoning,
        ),
    )


def test_kb_only_intent_never_allows_or_calls_web() -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.KNOWLEDGE_BASE_ONLY, allow_web=False),
        decisions=[decision(EvidenceStatus.INSUFFICIENT, AgentAction.INSUFFICIENT)],
    )
    web = WebSearchStub([])

    result = run(
        "只根据我的知识库回答",
        knowledge=KnowledgeSearchStub({"只根据我的知识库回答": []}),
        web=web,
        reasoning=reasoning,
    )

    assert web.queries == []
    assert AgentAction.WEB_SEARCH not in reasoning.decision_inputs[0]["allowed_actions"]
    assert result["tool_call_counts"] == {"knowledge_search": 1}


def test_c08_no_web_can_answer_from_kb_evidence() -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.KNOWLEDGE_BASE_ONLY, allow_web=False),
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, kb=[0])],
        answers=["过拟合是模型过度适配训练数据。"],
    )
    web = WebSearchStub([])
    question = "不要联网，根据知识库回答 什么是过拟合？"

    result = run(
        question,
        knowledge=KnowledgeSearchStub({question: [kb_result()]}),
        web=web,
        reasoning=reasoning,
    )

    assert reasoning.decision_inputs[0]["allowed_actions"] == [
        AgentAction.ANSWER,
        AgentAction.REWRITE_QUERY,
        AgentAction.GET_ARTICLE_CONTENT,
        AgentAction.INSUFFICIENT,
    ]
    assert web.queries == []
    assert result["final_answer"] == "过拟合是模型过度适配训练数据。"


def test_freshness_requires_web_before_answering() -> None:
    reasoning = ReasoningStub(
        intent=intent(
            AgentIntent.FRESH_INFORMATION,
            allow_web=True,
            requires_freshness=True,
        ),
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, web=[0])],
        answers=["当前版本是 2.0。"],
    )

    result = run(
        "当前版本是什么？",
        knowledge=KnowledgeSearchStub({"当前版本是什么？": [kb_result()]}),
        web=WebSearchStub([[web_result()]]),
        reasoning=reasoning,
    )

    assert len(reasoning.decision_inputs) == 1
    assert reasoning.decision_inputs[0]["web_evidence"]
    assert result["allow_web"] is True
    assert result["requires_freshness"] is True
    assert result["final_answer"] == "当前版本是 2.0。"


def test_sufficient_kb_can_answer_without_web() -> None:
    web = WebSearchStub([])
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, kb=[0])],
        answers=["知识库中的稳定事实。"],
    )

    result = run(
        "稳定事实是什么？",
        knowledge=KnowledgeSearchStub({"稳定事实是什么？": [kb_result()]}),
        web=web,
        reasoning=reasoning,
    )

    assert result["final_answer"] == "知识库中的稳定事实。"
    assert web.queries == []


def test_insufficient_kb_can_search_web_then_answer_with_web_source() -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.WEB_SEARCH),
            decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, web=[0]),
        ],
        answers=["当前版本是 2.0。"],
    )
    web = WebSearchStub([[web_result()]])

    result = run(
        "版本是什么？",
        knowledge=KnowledgeSearchStub({"版本是什么？": []}),
        web=web,
        reasoning=reasoning,
    )

    assert web.queries == ["版本是什么？"]
    assert result["tool_call_counts"] == {"knowledge_search": 1, "web_search": 1}
    assert result["sources"] == [
        {
            "source_type": "web",
            "title": "官方更新",
            "url": "https://example.com/update",
            "source": "example.com",
            "published_at": "2026-09-14",
        }
    ]


def test_empty_web_result_is_distinct_success_and_terminates() -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.WEB_SEARCH),
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.INSUFFICIENT),
        ],
    )

    result = run(
        "未知问题",
        knowledge=KnowledgeSearchStub({"未知问题": []}),
        web=WebSearchStub([[]]),
        reasoning=reasoning,
    )

    assert result["web_results"] == []
    assert result["last_tool_error"] is None
    assert result["last_error_type"] is None
    assert result["tool_call_counts"]["web_search"] == 1


def test_freshness_cannot_answer_from_kb_when_web_is_empty() -> None:
    reasoning = ReasoningStub(
        intent=intent(
            AgentIntent.FRESH_INFORMATION,
            allow_web=True,
            requires_freshness=True,
        ),
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, kb=[0])],
    )

    result = run(
        "当前状态是什么？",
        knowledge=KnowledgeSearchStub({"当前状态是什么？": [kb_result()]}),
        web=WebSearchStub([[]]),
        reasoning=reasoning,
    )

    assert AgentAction.ANSWER not in reasoning.decision_inputs[0]["allowed_actions"]
    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert reasoning.answer_inputs == []


def test_web_timeout_fails_safely_without_retry_or_detail_leak() -> None:
    reasoning = ReasoningStub(
        intent=intent(
            AgentIntent.FRESH_INFORMATION,
            allow_web=True,
            requires_freshness=True,
        ),
        decisions=[],
    )

    result = run(
        "今天 A 股怎么样？",
        knowledge=KnowledgeSearchStub({"今天 A 股怎么样？": []}),
        web=WebSearchStub([TimeoutError("敏感网络详情")]),
        reasoning=reasoning,
    )

    assert result["tool_call_counts"]["web_search"] == 1
    assert result["last_tool_error"] == "Web Search 执行失败（TimeoutError）"
    assert result["last_error_type"] is AgentErrorType.EXECUTION
    assert "敏感网络详情" not in result["final_answer"]
    assert reasoning.decision_inputs == []


def test_freshness_forces_web_before_stubbed_insufficient_decision() -> None:
    reasoning = ReasoningStub(
        intent=intent(
            AgentIntent.FRESH_INFORMATION,
            allow_web=True,
            requires_freshness=True,
        ),
        decisions=[decision(EvidenceStatus.INSUFFICIENT, AgentAction.INSUFFICIENT)],
    )
    web = WebSearchStub([[]])

    result = run(
        "今天 A 股茅台的股票情况怎么样？",
        knowledge=KnowledgeSearchStub(
            {"今天 A 股茅台的股票情况怎么样？": []}
        ),
        web=web,
        reasoning=reasoning,
    )

    assert web.queries == ["今天 A 股茅台的股票情况怎么样？"]
    assert len(reasoning.decision_inputs) == 1
    assert result["next_action"] is AgentAction.INSUFFICIENT


def test_nonfresh_insufficient_decision_is_not_forced_to_search_web() -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[decision(EvidenceStatus.INSUFFICIENT, AgentAction.INSUFFICIENT)],
    )
    web = WebSearchStub([])

    result = run(
        "普通知识问题",
        knowledge=KnowledgeSearchStub({"普通知识问题": []}),
        web=web,
        reasoning=reasoning,
    )

    assert web.queries == []
    assert len(reasoning.decision_inputs) == 1
    assert AgentAction.WEB_SEARCH in reasoning.decision_inputs[0]["allowed_actions"]
    assert result["next_action"] is AgentAction.INSUFFICIENT


def test_web_error_can_fall_back_to_kb_partial_without_losing_error_type() -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[
            decision(EvidenceStatus.PARTIAL, AgentAction.WEB_SEARCH),
            decision(EvidenceStatus.PARTIAL, AgentAction.ANSWER, kb=[0]),
        ],
        answers=["知识库只支持部分结论。"],
    )

    result = run(
        "复合问题",
        knowledge=KnowledgeSearchStub({"复合问题": [kb_result()]}),
        web=WebSearchStub([TimeoutError("provider-key=secret")]),
        reasoning=reasoning,
    )

    assert result["final_answer"].startswith("知识库只支持部分结论。")
    assert result["last_error_type"] is AgentErrorType.EXECUTION
    assert result["last_tool_result"]["error_type"] is AgentErrorType.EXECUTION
    assert "secret" not in result["final_answer"]


def test_second_web_search_is_rejected_by_program_budget() -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.WEB_SEARCH),
            decision(EvidenceStatus.PARTIAL, AgentAction.WEB_SEARCH),
        ],
    )
    web = WebSearchStub([[web_result()], [web_result()]])

    result = run(
        "预算问题",
        knowledge=KnowledgeSearchStub({"预算问题": []}),
        web=web,
        reasoning=reasoning,
    )

    assert web.queries == ["预算问题"]
    assert AgentAction.WEB_SEARCH not in reasoning.decision_inputs[1]["allowed_actions"]
    assert result["next_action"] is AgentAction.INSUFFICIENT


def test_web_action_is_rejected_when_intent_disables_it(
    caplog: Any,
) -> None:
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.KNOWLEDGE_BASE_ONLY, allow_web=False),
        decisions=[decision(EvidenceStatus.INSUFFICIENT, AgentAction.WEB_SEARCH)],
    )
    web = WebSearchStub([[web_result()]])

    with caplog.at_level(logging.ERROR, logger="app.agent.nodes"):
        result = run(
            "不要联网",
            knowledge=KnowledgeSearchStub({"不要联网": []}),
            web=web,
            reasoning=reasoning,
        )

    assert web.queries == []
    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert "next_action=web_search" in caplog.text
    assert "allowed_actions=['rewrite_query', 'insufficient']" in caplog.text
    assert "allow_web=False" in caplog.text
    assert "requires_freshness=False" in caplog.text
    assert "intent=knowledge_base_only" in caplog.text


def test_answer_receives_only_selected_web_snippet() -> None:
    first = web_result(title="选中结果", snippet="摘要只支持事实 A。")
    second = web_result(title="未选结果", snippet="另一条无关摘要。")
    reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.WEB_SEARCH),
            decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, web=[0]),
        ],
        answers=["摘要只支持事实 A。"],
    )

    result = run(
        "摘要问题",
        knowledge=KnowledgeSearchStub({"摘要问题": []}),
        web=WebSearchStub([[first, second]]),
        reasoning=reasoning,
    )

    assert reasoning.answer_inputs[0]["evidence"] == [
        {"source_type": "web", **first.model_dump(mode="json")}
    ]
    assert "事实 B" not in result["final_answer"]


def test_same_thread_resets_web_results_and_web_budget() -> None:
    graph = create_agent_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}
    first_reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[
            decision(EvidenceStatus.INSUFFICIENT, AgentAction.WEB_SEARCH),
            decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, web=[0]),
        ],
        answers=["第一答"],
    )
    run(
        "第一问",
        knowledge=KnowledgeSearchStub({"第一问": []}),
        web=WebSearchStub([[web_result(title="第一条")]]),
        reasoning=first_reasoning,
        graph=graph,
        config=config,
    )
    second_reasoning = ReasoningStub(
        intent=intent(AgentIntent.OPEN, allow_web=True),
        decisions=[decision(EvidenceStatus.SUFFICIENT, AgentAction.ANSWER, kb=[0])],
        answers=["第二答"],
    )

    result = run(
        "第二问",
        knowledge=KnowledgeSearchStub({"第二问": [kb_result()]}),
        web=WebSearchStub([]),
        reasoning=second_reasoning,
        graph=graph,
        config=config,
    )

    assert result["web_results"] == []
    assert result["tool_call_counts"] == {"knowledge_search": 1}
    assert result["step_count"] == 1
    assert [message.content for message in result["messages"]] == [
        "第一问",
        "第一答",
        "第二问",
        "第二答",
    ]
