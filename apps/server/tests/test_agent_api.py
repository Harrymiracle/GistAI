import logging
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

import app.agent.chat as chat_module
import app.api.deps as deps_module
from app.agent.chat import AgentChatService
from app.agent.context import AgentContext
from app.agent.schemas import AgentAction, AgentErrorType, EvidenceStatus
from app.api.deps import (
    get_agent_chat_service,
    get_agent_context,
    get_current_user_id,
)
from app.main import app


class RecordingGraphStub:
    """记录 Agent API 传入 Graph 的最小输入与隔离后的 checkpoint key。"""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self,
        graph_input: dict[str, Any],
        *,
        config: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        self.calls.append(
            {"input": graph_input, "config": config, "context": context}
        )
        return self.responses.pop(0)


class UnexpectedGraphStub:
    def invoke(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        raise RuntimeError("不得暴露的 provider 密钥与堆栈")


class DependencyStub:
    pass


def graph_result(
    *,
    answer: str = "这是回答。",
    evidence_status: EvidenceStatus = EvidenceStatus.SUFFICIENT,
    next_action: AgentAction = AgentAction.ANSWER,
    sources: list[dict[str, Any]] | None = None,
    last_error_type: AgentErrorType | None = None,
) -> dict[str, Any]:
    return {
        "final_answer": answer,
        "evidence_status": evidence_status,
        "next_action": next_action,
        "sources": sources or [],
        "last_error_type": last_error_type,
    }


def build_client(graph: object, *, user_id: int = 41) -> TestClient:
    context = AgentContext(
        knowledge_search=DependencyStub(),
        web_search=DependencyStub(),
        reasoning=DependencyStub(),
    )
    app.dependency_overrides[get_agent_chat_service] = lambda: AgentChatService(graph)
    app.dependency_overrides[get_agent_context] = lambda: context
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


def test_agent_context_injects_decision_thinking_setting(monkeypatch) -> None:
    captured: dict[str, bool] = {}
    reasoning = DependencyStub()

    def build_reasoning(
        _client: object,
        *,
        decision_enable_thinking: bool = True,
    ) -> DependencyStub:
        captured["decision_enable_thinking"] = decision_enable_thinking
        return reasoning

    monkeypatch.setattr(deps_module, "AgentReasoningService", build_reasoning)
    monkeypatch.setattr(
        deps_module.settings,
        "agent_decision_enable_thinking",
        False,
    )

    context = get_agent_context(
        session=DependencyStub(),
        user_id=41,
        embedding_service=DependencyStub(),
        web_search_service=DependencyStub(),
        crawler_service=DependencyStub(),
    )

    assert context.reasoning is reasoning
    assert captured == {"decision_enable_thinking": False}


def test_first_chat_generates_thread_and_maps_sources() -> None:
    graph = RecordingGraphStub(
        [
            graph_result(
                sources=[
                    {"article_id": 7, "chunk_id": 9, "title": "知识库文章"},
                    {
                        "source_type": "web",
                        "title": "外部资料",
                        "url": "https://example.com/news",
                        "source": "example.com",
                        "published_at": "2026-09-14",
                    },
                ]
            )
        ]
    )
    client = build_client(graph)

    response = client.post("/api/v1/agent/chat", json={"message": "  问题  "})

    assert response.status_code == 200
    data = response.json()["data"]
    thread_id = UUID(data["thread_id"])
    assert data == {
        "thread_id": str(thread_id),
        "answer": "这是回答。",
        "status": "answer",
        "sources": [
            {
                "source_type": "knowledge_base",
                "title": "知识库文章",
                "article_id": 7,
                "chunk_id": 9,
                "url": None,
                "source": None,
                "published_at": None,
            },
            {
                "source_type": "web",
                "title": "外部资料",
                "article_id": None,
                "chunk_id": None,
                "url": "https://example.com/news",
                "source": "example.com",
                "published_at": "2026-09-14",
            },
        ],
    }
    assert graph.calls[0]["input"] == {
        "messages": [{"role": "user", "content": "问题"}],
        "allow_web_override": None,
    }
    assert graph.calls[0]["config"]["configurable"]["thread_id"] == (
        f"41:{thread_id}"
    )


def test_agent_chat_logs_total_duration_without_message_content(
    monkeypatch,
    caplog,
) -> None:
    graph = RecordingGraphStub([graph_result()])
    context = AgentContext(
        knowledge_search=DependencyStub(),
        web_search=DependencyStub(),
        reasoning=DependencyStub(),
    )
    times = iter([40.0, 40.75])
    monkeypatch.setattr(
        chat_module,
        "time",
        SimpleNamespace(perf_counter=lambda: next(times)),
        raising=False,
    )
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    result = AgentChatService(graph).chat(
        "不得写入日志的完整用户消息",
        None,
        user_id=41,
        context=context,
    )

    assert result.answer == "这是回答。"
    assert "agent_chat duration_ms=750.00" in caplog.text
    assert "outcome=success" in caplog.text
    assert "不得写入日志的完整用户消息" not in caplog.text


def test_follow_up_reuses_thread_and_new_chat_uses_different_checkpoint() -> None:
    graph = RecordingGraphStub([graph_result(), graph_result(), graph_result()])
    client = build_client(graph, user_id=17)

    first = client.post("/api/v1/agent/chat", json={"message": "第一问"})
    thread_id = first.json()["data"]["thread_id"]
    follow_up = client.post(
        "/api/v1/agent/chat",
        json={"message": "追问", "thread_id": thread_id},
    )
    new_chat = client.post("/api/v1/agent/chat", json={"message": "新对话"})

    assert first.status_code == follow_up.status_code == new_chat.status_code == 200
    assert follow_up.json()["data"]["thread_id"] == thread_id
    assert new_chat.json()["data"]["thread_id"] != thread_id
    assert graph.calls[0]["config"] == graph.calls[1]["config"]
    assert graph.calls[0]["config"] != graph.calls[2]["config"]


@pytest.mark.parametrize("allow_web_override", [True, False, None])
def test_allow_web_override_enters_graph_input(
    allow_web_override: bool | None,
) -> None:
    graph = RecordingGraphStub([graph_result()])
    client = build_client(graph)

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "问题",
            "allow_web_override": allow_web_override,
        },
    )

    assert response.status_code == 200
    assert graph.calls[0]["input"]["allow_web_override"] is allow_web_override


def test_same_public_thread_is_isolated_between_users() -> None:
    thread_id = uuid4()
    graph = RecordingGraphStub([graph_result(), graph_result()])
    client = build_client(graph, user_id=17)

    first = client.post(
        "/api/v1/agent/chat",
        json={"message": "用户一", "thread_id": str(thread_id)},
    )
    app.dependency_overrides[get_current_user_id] = lambda: 18
    second = client.post(
        "/api/v1/agent/chat",
        json={"message": "用户二", "thread_id": str(thread_id)},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["thread_id"] == str(thread_id)
    assert second.json()["data"]["thread_id"] == str(thread_id)
    assert graph.calls[0]["config"]["configurable"]["thread_id"] == f"17:{thread_id}"
    assert graph.calls[1]["config"]["configurable"]["thread_id"] == f"18:{thread_id}"


def test_response_statuses_are_explicit() -> None:
    graph = RecordingGraphStub(
        [
            graph_result(
                evidence_status=EvidenceStatus.PARTIAL,
                next_action=AgentAction.PARTIAL_ANSWER,
            ),
            graph_result(
                evidence_status=EvidenceStatus.INSUFFICIENT,
                next_action=AgentAction.INSUFFICIENT,
            ),
            graph_result(
                evidence_status=EvidenceStatus.SUFFICIENT,
                next_action=AgentAction.ANSWER,
                last_error_type=AgentErrorType.EXECUTION,
            ),
        ]
    )
    client = build_client(graph)

    statuses = [
        client.post("/api/v1/agent/chat", json={"message": str(index)}).json()[
            "data"
        ]["status"]
        for index in range(3)
    ]

    assert statuses == ["partial", "insufficient", "error"]


def test_unexpected_failure_uses_safe_api_error(caplog) -> None:
    client = build_client(UnexpectedGraphStub())

    response = client.post("/api/v1/agent/chat", json={"message": "问题"})

    assert response.status_code == 500
    assert response.json() == {
        "code": 50002,
        "message": "Agent 暂时无法完成请求，请稍后重试",
        "data": None,
    }
    assert "provider" not in response.text
    assert "密钥" not in response.text
    assert "provider" not in caplog.text
    assert "密钥" not in caplog.text


def test_agent_chat_request_validation_is_strict() -> None:
    graph = RecordingGraphStub([])
    client = build_client(graph)

    invalid_payloads = [
        {"message": "   "},
        {"message": "x" * 4001},
        {"message": "问题", "thread_id": "not-a-uuid"},
        {"message": "问题", "allow_web_override": "yes"},
        {"message": "问题", "user_id": 999},
    ]

    for payload in invalid_payloads:
        response = client.post("/api/v1/agent/chat", json=payload)
        assert response.status_code == 422

    assert graph.calls == []


def teardown_module() -> None:
    app.dependency_overrides.clear()
