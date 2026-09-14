from collections.abc import Generator, Sequence
import logging
from uuid import UUID, uuid4

import psycopg
import pytest
from langchain_core.messages import BaseMessage
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from app.agent.chat import AgentChatService
from app.agent.checkpoint import (
    AgentCheckpointStartupError,
    postgres_checkpointer,
    to_psycopg_connection_string,
)
from app.agent.context import AgentContext
from app.agent.graph import create_agent_graph
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentIntent,
    EvidenceStatus,
    IntentDecision,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
)
from app.core.config import settings


class KnowledgeSearchStub:
    def search(self, payload: KnowledgeSearchInput) -> list[KnowledgeSearchResult]:
        return [
            KnowledgeSearchResult(
                article_id=1,
                chunk_id=1,
                title="持久化测试",
                chunk_text=f"{payload.query} 的可靠证据",
                score=0.99,
            )
        ]


class ReasoningStub:
    def __init__(self) -> None:
        self.conversations: list[list[str]] = []

    def classify_intent(self, **_options: object) -> IntentDecision:
        return IntentDecision(
            intent=AgentIntent.KNOWLEDGE_BASE_ONLY,
            allow_web=False,
            requires_freshness=False,
            reason="测试仅使用知识库",
        )

    def decide(
        self,
        *,
        conversation: Sequence[BaseMessage],
        **_options: object,
    ) -> AgentDecision:
        self.conversations.append([str(message.content) for message in conversation])
        return AgentDecision(
            evidence_status=EvidenceStatus.SUFFICIENT,
            reason="测试证据充分",
            next_action=AgentAction.ANSWER,
            selected_result_indexes=[0],
        )

    def rewrite_query(self, **_options: object) -> str:
        raise AssertionError("当前测试不应改写查询")

    def generate_answer(self, *, original_query: str, **_options: object) -> str:
        return f"回答：{original_query}"


class NoWebSearchStub:
    def search(self, _query: str) -> list[object]:
        raise AssertionError("当前测试不应访问 Web Search")


def context(reasoning: ReasoningStub) -> AgentContext:
    return AgentContext(
        knowledge_search=KnowledgeSearchStub(),
        web_search=NoWebSearchStub(),
        reasoning=reasoning,
    )


@pytest.fixture
def checkpoint_connection_string() -> Generator[str, None, None]:
    base_connection_string = to_psycopg_connection_string(settings.database_url)
    connection_options = conninfo_to_dict(base_connection_string)
    assert connection_options.get("host") in {
        "localhost",
        "127.0.0.1",
    }
    test_database = f"gistai_checkpoint_test_{uuid4().hex}"
    admin_options = {**connection_options, "dbname": "postgres"}
    with psycopg.connect(**admin_options, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_database))
        )
    test_url = make_url(settings.database_url).set(database=test_database)
    try:
        yield to_psycopg_connection_string(
            test_url.render_as_string(hide_password=False)
        )
    finally:
        with psycopg.connect(**admin_options, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (test_database,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(test_database))
            )


def test_sqlalchemy_postgres_url_is_converted_for_psycopg() -> None:
    result = to_psycopg_connection_string(
        "postgresql+psycopg://user:password@db.example/gistai"
    )

    assert result == "postgresql://user:password@db.example/gistai"


def test_checkpoint_startup_failure_is_safe_and_closes_pool(
    monkeypatch,
    caplog,
) -> None:
    closed: list[bool] = []

    class FailingPool:
        def __init__(self, **_options: object) -> None:
            pass

        def open(self, **_options: object) -> None:
            logging.getLogger("psycopg.pool").error(
                "secret-db-host:5432 user=private"
            )
            raise RuntimeError("secret-db-host:5432 private SQL")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr("app.agent.checkpoint.ConnectionPool", FailingPool)

    with pytest.raises(AgentCheckpointStartupError) as captured:
        with postgres_checkpointer("postgresql://user:password@localhost/db"):
            raise AssertionError("初始化失败时不应进入 Runtime")

    assert str(captured.value) == "Agent checkpoint 初始化失败"
    assert "secret-db-host" not in str(captured.value)
    assert "secret-db-host" not in caplog.text
    assert "user=private" not in caplog.text
    assert closed == [True]


def test_checkpoint_setup_is_guarded_by_postgres_advisory_lock(monkeypatch) -> None:
    events: list[str] = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def execute(self, query: str, _params: object) -> None:
            events.append(query)

    class FakePool:
        def __init__(self, **_options: object) -> None:
            pass

        def open(self, **_options: object) -> None:
            events.append("open")

        def connection(self) -> FakeConnection:
            return FakeConnection()

        def close(self) -> None:
            events.append("close")

    class FakeSaver:
        def __init__(self, *_args: object, **_options: object) -> None:
            pass

        def setup(self) -> None:
            events.append("setup")

    monkeypatch.setattr("app.agent.checkpoint.ConnectionPool", FakePool)
    monkeypatch.setattr("app.agent.checkpoint.PostgresSaver", FakeSaver)

    with postgres_checkpointer("postgresql://user:password@localhost/db"):
        events.append("yield")

    assert events == [
        "open",
        "SELECT pg_advisory_lock(%s)",
        "setup",
        "SELECT pg_advisory_unlock(%s)",
        "yield",
        "close",
    ]


def test_graph_and_checkpointer_recreation_recovers_conversation(
    checkpoint_connection_string: str,
) -> None:
    public_thread_id = uuid4()
    internal_thread_id = f"51:{public_thread_id}"
    first_reasoning = ReasoningStub()

    with postgres_checkpointer(checkpoint_connection_string) as first_saver:
        first_service = AgentChatService(create_agent_graph(first_saver))
        first_service.chat(
            "第一问",
            public_thread_id,
            user_id=51,
            context=context(first_reasoning),
        )

    second_reasoning = ReasoningStub()
    with postgres_checkpointer(checkpoint_connection_string) as second_saver:
        second_graph = create_agent_graph(second_saver)
        second_service = AgentChatService(second_graph)
        second_service.chat(
            "追问",
            public_thread_id,
            user_id=51,
            context=context(second_reasoning),
        )
        state = second_graph.get_state(
            {"configurable": {"thread_id": internal_thread_id}}
        ).values

    assert second_reasoning.conversations == [
        ["第一问", "回答：第一问", "追问"]
    ]
    assert [str(message.content) for message in state["messages"]] == [
        "第一问",
        "回答：第一问",
        "追问",
        "回答：追问",
    ]
    assert state["original_query"] == "追问"
    assert state["step_count"] == 1
    assert state["tool_call_counts"] == {"knowledge_search": 1}
    assert state["sources"] == [
        {"article_id": 1, "chunk_id": 1, "title": "持久化测试"}
    ]


def test_postgres_checkpoint_isolates_threads_and_users(
    checkpoint_connection_string: str,
) -> None:
    shared_uuid = uuid4()
    other_uuid = uuid4()
    identities = [
        (61, shared_uuid, "用户一"),
        (61, other_uuid, "另一线程"),
        (62, shared_uuid, "用户二"),
    ]
    with postgres_checkpointer(checkpoint_connection_string) as saver:
        graph = create_agent_graph(saver)
        service = AgentChatService(graph)
        reasonings: list[ReasoningStub] = []
        for user_id, thread_id, question in identities:
            reasoning = ReasoningStub()
            reasonings.append(reasoning)
            service.chat(
                question,
                UUID(str(thread_id)),
                user_id=user_id,
                context=context(reasoning),
            )

    assert [reasoning.conversations for reasoning in reasonings] == [
        [["用户一"]],
        [["另一线程"]],
        [["用户二"]],
    ]
