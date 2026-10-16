import logging
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

import app.agent.graph as graph_module
from app.agent.chat import AgentChatService
from app.agent.context import AgentContext
from app.agent.graph import create_agent_graph
from app.agent.nodes import initialize
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentIntent,
    EvidenceStatus,
    IntentDecision,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
)


class EmptyKnowledgeSearchStub:
    def search(
        self,
        _payload: KnowledgeSearchInput,
    ) -> list[KnowledgeSearchResult]:
        return []


class NoWebSearchStub:
    def search(self, _query: str) -> list[object]:
        raise AssertionError("当前测试不应调用 Web Search")


class InsufficientReasoningStub:
    def classify_intent(self, **_options: object) -> IntentDecision:
        return IntentDecision(
            intent=AgentIntent.KNOWLEDGE_BASE_ONLY,
            allow_web=False,
            requires_freshness=False,
            reason="测试仅使用知识库",
        )

    def decide(self, **_options: object) -> AgentDecision:
        return AgentDecision(
            evidence_status=EvidenceStatus.INSUFFICIENT,
            reason="没有候选证据",
            next_action=AgentAction.INSUFFICIENT,
        )

    def rewrite_query(self, **_options: object) -> str:
        raise AssertionError("不应改写查询")

    def generate_answer(self, **_options: object) -> str:
        raise AssertionError("不应生成事实回答")


def empty_search_context() -> AgentContext:
    return AgentContext(
        knowledge_search=EmptyKnowledgeSearchStub(),
        web_search=NoWebSearchStub(),
        reasoning=InsufficientReasoningStub(),
    )


def test_agent_graph_runs_to_end_with_insufficient_answer(caplog) -> None:
    graph = create_agent_graph(InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}}
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    result = graph.invoke(
        {"messages": [{"role": "user", "content": "What is Agent Memory?"}]},
        config=config,
        context=empty_search_context(),
    )

    assert "无法" in result["final_answer"]
    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT
    for node_name in (
        "initial_decision",
        "contextualize_query",
        "knowledge_search",
        "evaluate_and_decide",
        "insufficient_answer",
    ):
        assert f"node={node_name}" in caplog.text


def test_profile_node_uses_perf_counter_and_preserves_result(
    monkeypatch,
    caplog,
) -> None:
    profile_node = getattr(graph_module, "profile_node", None)
    assert profile_node is not None
    times = iter([10.0, 10.125])
    monkeypatch.setattr(
        graph_module,
        "time",
        type("FakeTime", (), {"perf_counter": staticmethod(lambda: next(times))}),
        raising=False,
    )
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    expected = {"current_query": "保持不变"}

    result = profile_node("knowledge_search", lambda: expected)()

    assert result is expected
    assert "node=knowledge_search" in caplog.text
    assert "duration_ms=125.00" in caplog.text
    assert "outcome=success" in caplog.text


def test_initialize_sets_queries_and_control_defaults() -> None:
    result = initialize(
        {"messages": [HumanMessage(content="What is Agent Memory?")]}
    )

    assert result["original_query"] == "What is Agent Memory?"
    assert result["current_query"] == "What is Agent Memory?"
    assert result["intent"] is None
    assert result["allow_web"] is True
    assert result["allow_web_override"] is None
    assert result["requires_freshness"] is False
    assert result["kb_results"] == []
    assert result["web_results"] == []
    assert result["article_contents"] == []
    assert result["web_page_contents"] == []
    assert result["article_fulltext_evidence"] == []
    assert result["web_fulltext_evidence"] == []
    assert result["read_article_ids"] == []
    assert result["fetched_web_urls"] == []
    assert result["selected_evidence"] == []
    assert result["evidence_status"] is EvidenceStatus.UNKNOWN
    assert result["evidence_reason"] is None
    assert result["rewrite_count"] == 0
    assert result["step_count"] == 0
    assert result["tool_call_counts"] == {}
    assert result["allowed_actions"] == []
    assert result["next_action"] is None
    assert result["selected_article_result_index"] is None
    assert result["selected_web_page_result_index"] is None
    assert result["last_tool_error"] is None
    assert result["final_answer"] is None
    assert result["sources"] == []


def test_same_thread_uses_checkpoint_and_resets_run_state() -> None:
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

    assert result["original_query"] == "Follow-up question"
    assert result["current_query"] == "Follow-up question"
    assert len(result["messages"]) == 4
    assert result["step_count"] == 1
    assert result["tool_call_counts"]["knowledge_search"] == 1
    assert checkpoint.values["final_answer"] == result["final_answer"]
    assert checkpoint.values["current_query"] == "Follow-up question"
    assert checkpoint.values["step_count"] == 1
    assert checkpoint.values["tool_call_counts"]["knowledge_search"] == 1


class UnexpectedFastPathDependency:
    """Fast Path 命中时，任何运行时依赖都不应被访问。"""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"Fast Path 不应访问运行时依赖：{name}")


def fast_path_context() -> AgentContext:
    dependency = UnexpectedFastPathDependency()
    return AgentContext(
        knowledge_search=dependency,  # type: ignore[arg-type]
        web_search=dependency,  # type: ignore[arg-type]
        reasoning=dependency,  # type: ignore[arg-type]
        article_content=dependency,  # type: ignore[arg-type]
        web_page_fetch=dependency,  # type: ignore[arg-type]
        fulltext_selector=dependency,  # type: ignore[arg-type]
    )


def test_session_status_follow_up_uses_local_answer_without_runtime_dependencies() -> None:
    graph = create_agent_graph(InMemorySaver())
    service = AgentChatService(graph)
    thread_id = uuid4()
    context = fast_path_context()
    service.chat("你好", thread_id, user_id=41, context=context)

    response = service.chat(
        "你好，我现在还在上面的聊天上吗？",
        thread_id,
        user_id=41,
        context=context,
    )

    assert response.answer == "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"
    assert response.status == "answer"
    assert response.sources == []


@pytest.mark.parametrize(
    ("message", "expected_answer"),
    [
        ("还在原对话中吗？", "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("这是新对话吗？", "不是，这是已有对话的延续，前面的聊天内容还在。"),
    ],
)
def test_session_status_missing_variants_use_local_answer(
    message: str,
    expected_answer: str,
) -> None:
    graph = create_agent_graph(InMemorySaver())
    service = AgentChatService(graph)
    thread_id = uuid4()
    context = fast_path_context()
    service.chat("你好", thread_id, user_id=41, context=context)

    response = service.chat(message, thread_id, user_id=41, context=context)

    assert response.answer == expected_answer
    assert response.status == "answer"
    assert response.sources == []


@pytest.mark.parametrize(
    ("message", "has_history", "expected_answer"),
    [
        ("你好，我现在还在上面的聊天上吗？", False, "这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("我还在刚才的聊天里吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("我们还在刚才的对话吗?", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("您好， 我现在还在上面的聊天吗 ？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("请问，还是刚才那个聊天吗？", False, "这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("这是新的对话吗？", True, "不是，这是已有对话的延续，前面的聊天内容还在。"),
        ("这是新的对话吗？", False, "是的，这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("这是新聊天吗?", True, "不是，这是已有对话的延续，前面的聊天内容还在。"),
        ("我是不是开了一个新会话？", False, "是的，这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("你还记得我们刚才说的吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("你还记得我们刚才说的吗？", False, "这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("请问 你还记得前面的聊天吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("前面的聊天还在吗。", False, "这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("还在原来的对话中吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("还在原对话中吗？", False, "这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("我还在之前的聊天里吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("现在还是刚才那个聊天吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("这是新对话吗？", False, "是的，这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("这是新的聊天吗？", True, "不是，这是已有对话的延续，前面的聊天内容还在。"),
        ("这是一个新会话吗？", False, "是的，这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("之前的对话还在吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("你好，这是新对话吗？", True, "不是，这是已有对话的延续，前面的聊天内容还在。"),
        ("您好，还在原对话中吗？", True, "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"),
        ("嗨， 还在 原 对话 中 吗 ?", False, "这是当前对话的第一条消息，还没有之前的聊天内容。"),
        ("请问，这是一个新的聊天吗。", True, "不是，这是已有对话的延续，前面的聊天内容还在。"),
    ],
)
def test_session_status_variants_use_checkpoint_history(
    message: str,
    has_history: bool,
    expected_answer: str,
) -> None:
    graph = create_agent_graph(InMemorySaver())
    service = AgentChatService(graph)
    thread_id = uuid4()
    context = fast_path_context()
    if has_history:
        service.chat("你好", thread_id, user_id=41, context=context)

    response = service.chat(message, thread_id, user_id=41, context=context)
    checkpoint = graph.get_state(
        {"configurable": {"thread_id": f"41:{thread_id}"}}
    ).values

    assert response.answer == expected_answer
    assert response.status == "answer"
    assert response.sources == []
    assert checkpoint["messages"][-2].content == message
    assert checkpoint["messages"][-1].content == expected_answer
    assert checkpoint["tool_call_counts"] == {}


def test_session_status_does_not_share_history_between_users() -> None:
    graph = create_agent_graph(InMemorySaver())
    service = AgentChatService(graph)
    thread_id = uuid4()
    context = fast_path_context()
    service.chat("你好", thread_id, user_id=41, context=context)

    response = service.chat(
        "这是新的对话吗？", thread_id, user_id=42, context=context
    )

    assert response.answer == "是的，这是当前对话的第一条消息，还没有之前的聊天内容。"
    assert len(graph.get_state(
        {"configurable": {"thread_id": f"42:{thread_id}"}}
    ).values["messages"]) == 2


def test_session_status_first_request_without_thread_id_creates_checkpoint() -> None:
    graph = create_agent_graph(InMemorySaver())
    service = AgentChatService(graph)
    response = service.chat(
        "这是新的对话吗？", None, user_id=41, context=fast_path_context()
    )

    assert response.answer == "是的，这是当前对话的第一条消息，还没有之前的聊天内容。"
    assert response.status == "answer"
    assert len(graph.get_state(
        {"configurable": {"thread_id": f"41:{response.thread_id}"}}
    ).values["messages"]) == 2


def test_session_status_answer_is_available_to_next_turn() -> None:
    graph = create_agent_graph(InMemorySaver())
    service = AgentChatService(graph)
    thread_id = uuid4()
    context = fast_path_context()
    first = service.chat("这是新的对话吗？", thread_id, user_id=41, context=context)

    second = service.chat("我还在刚才的聊天里吗？", thread_id, user_id=41, context=context)

    assert first.answer == "是的，这是当前对话的第一条消息，还没有之前的聊天内容。"
    assert second.answer == "是的，你还在当前对话中，前面的聊天内容还在，我们可以接着聊。"
    assert len(graph.get_state(
        {"configurable": {"thread_id": f"41:{thread_id}"}}
    ).values["messages"]) == 4


@pytest.mark.parametrize(
    "message",
    [
        "你好，帮我总结这篇文章",
        "人工智能是什么",
        "刚才提到的 Transformer 是什么",
        "我们刚才聊了什么",
        "帮我总结一下刚才的聊天",
        "你好，现在帮我查一下人工智能是什么",
        "前面的聊天还在吗？另外解释一下 Transformer",
        "你好，人工智能是什么",
        "帮我总结刚才的聊天",
        "请问现在的人工智能发展到什么阶段了",
        "原对话中提到的 Python 装饰器是什么",
    ],
)
def test_session_status_does_not_capture_real_tasks(message: str) -> None:
    graph = create_agent_graph(InMemorySaver())
    result = graph.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": str(uuid4())}},
        context=empty_search_context(),
    )

    assert result["tool_call_counts"] == {"knowledge_search": 1}


@pytest.mark.parametrize(
    ("message", "expected_answer"),
    [
        ("你好", "你好，有什么想了解的吗？"),
        ("你好！", "你好，有什么想了解的吗？"),
        ("HELLO", "你好，有什么想了解的吗？"),
        ("H E L L O", "你好，有什么想了解的吗？"),
        ("h i", "你好，有什么想了解的吗？"),
        ("B Y E", "再见，有需要随时来问我。"),
        ("你好啊", "你好，有什么想了解的吗？"),
        ("你好呀", "你好，有什么想了解的吗？"),
        ("你好哦", "你好，有什么想了解的吗？"),
        ("您好啊", "你好，有什么想了解的吗？"),
        ("您好呀", "你好，有什么想了解的吗？"),
        ("hi呀", "你好，有什么想了解的吗？"),
        ("hello呀", "你好，有什么想了解的吗？"),
        ("谢谢", "不客气。"),
        ("再见", "再见，有需要随时来问我。"),
        (
            "你是谁？",
            "我是 GistAI，可以基于你的知识库回答问题，并在允许时联网补充资料。",
        ),
        (
            "你能做什么？",
            "我可以基于你保存的文章进行检索和回答，也可以在允许联网时补充网页资料。",
        ),
        ("烦死了", "有什么具体问题可以直接告诉我。"),
        ("滚", "如果你有具体问题，可以直接说。"),
        ("你真烦", "如果你有具体问题，可以直接说。"),
    ],
)
def test_pure_short_inputs_use_fixed_fast_path_response(
    message: str,
    expected_answer: str,
) -> None:
    graph = create_agent_graph()

    result = graph.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": str(uuid4())}},
        context=fast_path_context(),
    )

    assert result["final_answer"] == expected_answer
    assert result["evidence_status"] is EvidenceStatus.SUFFICIENT
    assert result["next_action"] is AgentAction.ANSWER
    assert result["step_count"] == 0
    assert result["tool_call_counts"] == {}
    assert [item.content for item in result["messages"]] == [
        message,
        expected_answer,
    ]


@pytest.mark.parametrize("allow_web", [True, False])
def test_fast_path_is_independent_of_web_permission(allow_web: bool) -> None:
    graph = create_agent_graph()

    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "hi"}],
            "allow_web": allow_web,
            "allow_web_override": not allow_web,
        },
        config={"configurable": {"thread_id": str(uuid4())}},
        context=fast_path_context(),
    )

    assert result["final_answer"] == "你好，有什么想了解的吗？"
    assert result["allow_web"] is allow_web
    assert result["allow_web_override"] is None


@pytest.mark.parametrize(
    "message",
    [
        "hello world",
        "hello harness",
        "rag pipeline",
        "你好，我想问一下 Harness",
        "你好我想问一下 RAG",
        "谢谢，那第二阶段呢？",
        "这个 RAG 怎么这么蠢，到底哪里有问题？",
        "这篇文章写得真垃圾，它主要观点是什么？",
    ],
)
def test_knowledge_questions_do_not_match_fast_path(message: str) -> None:
    graph = create_agent_graph()

    result = graph.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": str(uuid4())}},
        context=empty_search_context(),
    )

    assert result["tool_call_counts"] == {"knowledge_search": 1}
    assert result["original_query"] == message
    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT
