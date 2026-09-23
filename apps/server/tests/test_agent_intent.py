import pytest
from pydantic import BaseModel

from app.agent.reasoning import AgentReasoningService
from app.agent.schemas import AgentIntent
from app.ai.errors import LLMResponseError


class RecordingLLMClient:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, str]] = []
        self.response_schemas: list[type[BaseModel] | None] = []
        self.purposes: list[str] = []
        self.thinking_overrides: list[bool | None] = []

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_schema: type[BaseModel] | None = None,
        purpose: str = "unspecified",
        enable_thinking: bool | None = None,
    ) -> str:
        self.calls.append((system_prompt, user_prompt))
        self.response_schemas.append(response_schema)
        self.purposes.append(purpose)
        self.thinking_overrides.append(enable_thinking)
        return self.responses.pop(0)


@pytest.mark.parametrize(
    "query",
    [
        "只根据我的知识库回答 Agent Memory",
        "只根据我保存的文章回答",
        "我之前收藏的资料里有没有提到 Agent Memory",
        "我保存的文章里是怎么说的？",
        "不要联网，只看我保存的内容",
        "不要搜索外部资料",
    ],
)
def test_explicit_knowledge_base_only_intent_disables_web(query: str) -> None:
    client = RecordingLLMClient()

    result = AgentReasoningService(client).classify_intent(
        query=query,
        conversation=[],
    )

    assert result.intent is AgentIntent.KNOWLEDGE_BASE_ONLY
    assert result.allow_web is False
    assert result.requires_freshness is False
    assert client.calls == []


@pytest.mark.parametrize(
    "query",
    [
        "LangGraph 最新版本是什么？",
        "当前 LangGraph 版本是多少？",
        "最近 Agent Memory 有什么进展？",
        "目前版本支持什么？",
    ],
)
def test_explicit_freshness_intent_allows_web(query: str) -> None:
    client = RecordingLLMClient()

    result = AgentReasoningService(client).classify_intent(
        query=query,
        conversation=[],
    )

    assert result.intent is AgentIntent.FRESH_INFORMATION
    assert result.allow_web is True
    assert result.requires_freshness is True
    assert client.calls == []


def test_explicit_no_web_overrides_freshness_permission() -> None:
    result = AgentReasoningService(RecordingLLMClient()).classify_intent(
        query="不要联网，只根据知识库告诉我最新版本",
        conversation=[],
    )

    assert result.intent is AgentIntent.KNOWLEDGE_BASE_ONLY
    assert result.allow_web is False
    assert result.requires_freshness is True


def test_ambiguous_intent_uses_structured_llm_classification() -> None:
    client = RecordingLLMClient(
        ['{"intent":"open","reason":"普通开放式问题"}']
    )

    result = AgentReasoningService(client).classify_intent(
        query="解释一下 Agent Memory",
        conversation=[],
    )

    assert result.intent is AgentIntent.OPEN
    assert result.allow_web is True
    assert result.requires_freshness is False
    assert len(client.calls) == 1
    assert client.response_schemas == [None]
    assert client.purposes == ["intent"]
    assert client.thinking_overrides == [False]


def test_present_tense_wording_without_freshness_semantics_uses_llm() -> None:
    client = RecordingLLMClient(
        ['{"intent":"open","reason":"只是表达当前阅读意愿"}']
    )

    result = AgentReasoningService(client).classify_intent(
        query="我现在想了解 Agent Memory 的定义",
        conversation=[],
    )

    assert result.intent is AgentIntent.OPEN
    assert result.requires_freshness is False
    assert len(client.calls) == 1


def test_ambiguous_intent_rejects_invalid_structured_output() -> None:
    client = RecordingLLMClient(['{"intent":"unknown","reason":"无法判断"}'])

    with pytest.raises(LLMResponseError, match="Intent 分类结果无效"):
        AgentReasoningService(client).classify_intent(
            query="解释一下 Agent Memory",
            conversation=[],
        )
