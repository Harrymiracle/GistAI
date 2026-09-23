from collections.abc import Sequence
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import BaseMessage, HumanMessage

from app.agent.context import AgentContext
from app.agent.graph import create_agent_graph
from app.agent.nodes import initial_decision, initialize
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentIntent,
    EvidenceStatus,
    IntentDecision,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
)


class RecordingReasoningStub:
    def __init__(self) -> None:
        self.intent_calls = 0

    def classify_intent(self, **_options: object) -> IntentDecision:
        self.intent_calls += 1
        return IntentDecision(
            intent=AgentIntent.KNOWLEDGE_BASE_ONLY,
            allow_web=False,
            requires_freshness=False,
            reason="旧 Intent 分类结果不应影响规则策略",
        )

    def contextualize_query(
        self,
        *,
        original_query: str,
        conversation: Sequence[BaseMessage],
    ) -> str:
        return original_query

    def decide(self, **_options: object) -> AgentDecision:
        return AgentDecision(
            evidence_status=EvidenceStatus.INSUFFICIENT,
            reason="测试结束当前轮次",
            next_action=AgentAction.INSUFFICIENT,
        )

    def rewrite_query(self, **_options: object) -> str:
        raise AssertionError("当前测试不应改写查询")

    def generate_answer(self, **_options: object) -> str:
        raise AssertionError("当前测试不应生成事实回答")


class EmptyKnowledgeSearchStub:
    def search(
        self,
        _payload: KnowledgeSearchInput,
    ) -> list[KnowledgeSearchResult]:
        return []


class NoWebSearchStub:
    def search(self, _query: str) -> list[object]:
        raise AssertionError("当前测试不应执行 Web Search")


def _resolve_turn(
    query: str,
    *,
    allow_web: bool | None = None,
    requires_freshness: bool | None = None,
    allow_web_override: bool | None = None,
) -> tuple[dict[str, object], RecordingReasoningStub]:
    state: dict[str, object] = {
        "messages": [HumanMessage(content=query)],
        "allow_web_override": allow_web_override,
    }
    if allow_web is not None:
        state["allow_web"] = allow_web
    if requires_freshness is not None:
        state["requires_freshness"] = requires_freshness

    initialized = initialize(state)  # type: ignore[arg-type]
    reasoning = RecordingReasoningStub()
    runtime = SimpleNamespace(context=SimpleNamespace(reasoning=reasoning))
    decision = initial_decision(
        {**state, **initialized},  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
    )
    return {**initialized, **decision}, reasoning


@pytest.mark.parametrize(
    ("query", "previous_allow_web", "previous_freshness", "expected"),
    [
        ("大语言模型怎么训练的？", None, None, (True, False)),
        ("不要联网，只根据我的资料回答", None, None, (False, False)),
        ("最近 OpenAI 有什么变化？", None, None, (True, True)),
        ("帮我上网查一下 LangGraph", None, None, (True, False)),
        ("不要联网，只根据我的资料告诉我最新情况", None, None, (False, True)),
        ("结合我的资料说一下", None, None, (True, False)),
        ("那第二阶段呢？", None, None, (True, False)),
        ("那继续说", False, False, (False, False)),
        ("这次可以联网查", False, False, (True, False)),
        ("再具体一点", True, True, (True, True)),
        ("不需要最新信息了", True, True, (True, False)),
        ("不用查最新的，但可以联网看看相关资料", False, True, (True, False)),
        ("不要联网，但我要知道现在是否还成立", True, False, (False, True)),
    ],
)
def test_intent_policy_uses_rules_defaults_and_explicit_overrides(
    query: str,
    previous_allow_web: bool | None,
    previous_freshness: bool | None,
    expected: tuple[bool, bool],
) -> None:
    result, reasoning = _resolve_turn(
        query,
        allow_web=previous_allow_web,
        requires_freshness=previous_freshness,
    )

    assert (result["allow_web"], result["requires_freshness"]) == expected
    assert reasoning.intent_calls == 0


@pytest.mark.parametrize(
    (
        "query",
        "session_allow_web",
        "allow_web_override",
        "expected_allow_web",
        "expected_freshness",
    ),
    [
        ("不要联网，只根据知识库回答", False, True, False, False),
        ("继续回答", True, False, False, False),
        ("继续回答", False, True, True, False),
        ("继续回答", False, None, False, False),
        ("继续回答", None, None, True, False),
        ("告诉我最新进展", True, False, False, True),
    ],
)
def test_allow_web_override_uses_explicit_priority_without_changing_freshness(
    query: str,
    session_allow_web: bool | None,
    allow_web_override: bool | None,
    expected_allow_web: bool,
    expected_freshness: bool,
) -> None:
    result, reasoning = _resolve_turn(
        query,
        allow_web=session_allow_web,
        allow_web_override=allow_web_override,
    )

    assert result["allow_web"] is expected_allow_web
    assert result["requires_freshness"] is expected_freshness
    assert result["allow_web_override"] is None
    assert reasoning.intent_calls == 0


@pytest.mark.parametrize(
    "query",
    [
        "今天 A 股怎么样？",
        "今天贵州茅台怎么样？",
        "今天 A 股茅台的股票情况怎么样？",
        "今天的 A 股怎么样？",
    ],
)
def test_today_questions_require_freshness_with_web_enabled(query: str) -> None:
    result, reasoning = _resolve_turn(query, allow_web_override=True)

    assert result["requires_freshness"] is True
    assert result["allow_web"] is True
    assert reasoning.intent_calls == 0


def test_today_question_respects_disabled_web_override() -> None:
    result, reasoning = _resolve_turn(
        "今天 A 股茅台的股票情况怎么样？",
        allow_web_override=False,
    )

    assert result["requires_freshness"] is True
    assert result["allow_web"] is False
    assert reasoning.intent_calls == 0


def test_explicit_no_web_wins_while_today_still_requires_freshness() -> None:
    result, reasoning = _resolve_turn(
        "这次不要联网，今天 A 股怎么样？",
        allow_web_override=True,
    )

    assert result["requires_freshness"] is True
    assert result["allow_web"] is False
    assert reasoning.intent_calls == 0


def _context(reasoning: RecordingReasoningStub) -> AgentContext:
    return AgentContext(
        knowledge_search=EmptyKnowledgeSearchStub(),
        web_search=NoWebSearchStub(),
        reasoning=reasoning,
    )


_MISSING = object()


def _invoke(
    graph,
    config: dict[str, dict[str, str]],
    query: str,
    reasoning: RecordingReasoningStub,
    *,
    allow_web_override: bool | None | object = _MISSING,
) -> dict[str, object]:
    graph_input: dict[str, object] = {
        "messages": [{"role": "user", "content": query}]
    }
    if allow_web_override is not _MISSING:
        graph_input["allow_web_override"] = allow_web_override

    return graph.invoke(
        graph_input,
        config=config,
        context=_context(reasoning),
    )


def test_same_thread_inherits_policy_and_explicit_overrides_replace_it() -> None:
    graph = create_agent_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}
    reasoning = RecordingReasoningStub()

    first = _invoke(
        graph,
        config,
        "不要联网，只根据我的资料回答",
        reasoning,
    )
    second = _invoke(graph, config, "那继续说", reasoning)
    third = _invoke(graph, config, "这次可以联网查", reasoning)
    fourth = _invoke(graph, config, "最近 OpenAI 有什么变化？", reasoning)
    fifth = _invoke(graph, config, "再具体一点", reasoning)
    sixth = _invoke(graph, config, "不需要最新信息了", reasoning)

    assert first["allow_web"] is False
    assert second["allow_web"] is False
    assert third["allow_web"] is True
    assert fourth["requires_freshness"] is True
    assert fifth["requires_freshness"] is True
    assert sixth["requires_freshness"] is False
    assert reasoning.intent_calls == 0


def test_different_threads_keep_policy_isolated() -> None:
    graph = create_agent_graph()
    thread_a = {"configurable": {"thread_id": str(uuid4())}}
    thread_b = {"configurable": {"thread_id": str(uuid4())}}
    reasoning = RecordingReasoningStub()

    result_a = _invoke(
        graph,
        thread_a,
        "不要联网，只根据我的资料回答",
        reasoning,
    )
    result_b = _invoke(graph, thread_b, "大语言模型怎么训练的？", reasoning)
    follow_up_a = _invoke(graph, thread_a, "继续", reasoning)

    assert result_a["allow_web"] is False
    assert result_b["allow_web"] is True
    assert result_b["requires_freshness"] is False
    assert follow_up_a["allow_web"] is False
    assert reasoning.intent_calls == 0


def test_allow_web_override_is_consumed_without_leaking_to_next_turn() -> None:
    graph = create_agent_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}
    reasoning = RecordingReasoningStub()

    first = _invoke(
        graph,
        config,
        "继续回答",
        reasoning,
        allow_web_override=False,
    )
    second = _invoke(graph, config, "这次可以联网查", reasoning)

    assert first["allow_web"] is False
    assert first["allow_web_override"] is None
    assert second["allow_web"] is True
    assert second["allow_web_override"] is None
