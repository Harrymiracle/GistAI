import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agent.reasoning import AgentReasoningService
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    EvidenceStatus,
    QueryRewriteResult,
)
from app.ai.errors import LLMResponseError


class SequencedLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
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
        return next(self._responses)


def _next_action_enum(response_schema: type[BaseModel] | None) -> list[str]:
    assert response_schema is not None
    schema = response_schema.model_json_schema()
    next_action_schema = schema["properties"]["next_action"]
    if "$ref" in next_action_schema:
        definition_name = next_action_schema["$ref"].rsplit("/", 1)[-1]
        next_action_schema = schema["$defs"][definition_name]
    if "const" in next_action_schema:
        return [next_action_schema["const"]]
    return next_action_schema["enum"]


@pytest.mark.parametrize("decision_thinking", [True, False])
def test_reasoning_service_applies_decision_thinking_without_affecting_other_calls(
    decision_thinking: bool,
) -> None:
    client = SequencedLLMClient(
        [
            (
                '{"evidence_status":"sufficient","reason":"知识库证据足够",'
                '"next_action":"answer","selected_result_indexes":[0],'
                '"selected_web_result_indexes":[],'
                '"selected_article_result_index":null,'
                '"selected_web_page_result_index":null,'
                '"selected_article_content_indexes":[],'
                '"selected_web_page_content_indexes":[]}'
            ),
            '{"query":"Agent Memory 的工作机制"}',
            '{"answer":"Agent Memory 会保存对话上下文。"}',
        ]
    )
    service = AgentReasoningService(
        client,
        decision_enable_thinking=decision_thinking,
    )
    evidence = [
        {
            "article_id": 11,
            "chunk_id": 101,
            "title": "Agent Memory",
            "chunk_text": "Agent Memory 会保存对话上下文。",
            "score": 0.91,
        }
    ]

    decision = service.decide(
        original_query="Agent Memory 是什么？",
        current_query="Agent Memory 是什么？",
        kb_evidence=evidence,
        web_evidence=[
            {
                "title": "官方更新",
                "url": "https://example.com/update",
                "snippet": "这是搜索结果摘要。",
                "source": "example.com",
                "published_at": "2026-09-14",
            }
        ],
        article_fulltext_evidence=[],
        web_fulltext_evidence=[],
        allowed_actions=[AgentAction.ANSWER, AgentAction.REWRITE_QUERY],
        conversation=[],
    )
    rewritten = service.rewrite_query(
        original_query="Agent Memory 是什么？",
        current_query="Agent Memory 是什么？",
        conversation=[],
    )
    answer = service.generate_answer(
        original_query="Agent Memory 是什么？",
        evidence=evidence,
        evidence_status=EvidenceStatus.PARTIAL,
        conversation=[],
    )

    assert decision.evidence_status is EvidenceStatus.SUFFICIENT
    assert decision.next_action is AgentAction.ANSWER
    assert decision.selected_result_indexes == [0]
    assert decision.selected_web_result_indexes == []
    assert decision.selected_article_result_index is None
    assert decision.selected_web_page_result_index is None
    assert decision.selected_article_content_indexes == []
    assert decision.selected_web_page_content_indexes == []
    decision_payload = json.loads(client.calls[0][1])
    assert decision_payload["knowledge_base_evidence"][0]["index"] == 0
    assert decision_payload["web_search_evidence"][0]["index"] == 0
    assert rewritten == "Agent Memory 的工作机制"
    assert answer == "Agent Memory 会保存对话上下文。"
    assert len(client.calls) == 3
    assert client.response_schemas[0] is not AgentDecision
    assert issubclass(client.response_schemas[0], AgentDecision)
    assert _next_action_enum(client.response_schemas[0]) == [
        AgentAction.ANSWER.value,
        AgentAction.REWRITE_QUERY.value,
    ]
    assert client.response_schemas[1:] == [None, None]
    assert client.purposes == [
        "agent_decision",
        "query_rewrite",
        "agent_answer",
    ]
    assert client.thinking_overrides == [decision_thinking, False, False]


def test_decision_call_override_disables_thinking_and_keeps_structured_output() -> None:
    client = SequencedLLMClient(
        [
            (
                '{"evidence_status":"insufficient","reason":"证据不足",'
                '"next_action":"insufficient","selected_result_indexes":[],'
                '"selected_web_result_indexes":[],'
                '"selected_article_result_index":null,'
                '"selected_web_page_result_index":null,'
                '"selected_article_content_indexes":[],'
                '"selected_web_page_content_indexes":[]}'
            )
        ]
    )
    service = AgentReasoningService(client, decision_enable_thinking=True)

    service.decide(
        original_query="问题",
        current_query="问题",
        kb_evidence=[],
        web_evidence=[],
        article_fulltext_evidence=[],
        web_fulltext_evidence=[],
        allowed_actions=[AgentAction.INSUFFICIENT],
        conversation=[],
        enable_thinking=False,
    )

    assert client.thinking_overrides == [False]
    assert client.response_schemas[0] is not AgentDecision
    assert issubclass(client.response_schemas[0], AgentDecision)
    assert _next_action_enum(client.response_schemas[0]) == [
        AgentAction.INSUFFICIENT.value
    ]
    decision_payload = json.loads(client.calls[0][1])
    assert decision_payload["valid_indexes"] == {
        "selected_result_indexes": [],
        "selected_web_result_indexes": [],
        "selected_article_content_indexes": [],
        "selected_web_page_content_indexes": [],
    }


def test_decision_payload_exposes_local_valid_indexes_without_chunk_indexes() -> None:
    client = SequencedLLMClient(
        [
            (
                '{"evidence_status":"insufficient","reason":"证据不足",'
                '"next_action":"insufficient","selected_result_indexes":[],'
                '"selected_web_result_indexes":[],'
                '"selected_article_result_index":null,'
                '"selected_web_page_result_index":null,'
                '"selected_article_content_indexes":[],'
                '"selected_web_page_content_indexes":[]}'
            )
        ]
    )
    service = AgentReasoningService(client)
    kb_evidence = [
        {
            "article_id": index + 1,
            "chunk_id": index + 101,
            "title": f"知识库 {index}",
            "chunk_text": "知识库证据",
            "score": 0.9,
        }
        for index in range(2)
    ]
    web_evidence = [
        {
            "title": f"网页 {index}",
            "url": f"https://example.com/{index}",
            "snippet": "网页摘要",
            "source": "example.com",
            "published_at": None,
        }
        for index in range(3)
    ]
    article_fulltext_evidence = [
        {
            "source_type": "knowledge_base_fulltext",
            "content": "知识库全文证据",
            "token_count": 10,
            "temporary_chunk_indexes": [7, 8],
            "article_id": 1,
        }
    ]
    web_fulltext_evidence = [
        {
            "source_type": "web_fulltext",
            "content": "网页全文证据",
            "token_count": 10,
            "temporary_chunk_indexes": [index + 20],
            "url": f"https://example.com/full/{index}",
        }
        for index in range(4)
    ]

    service.decide(
        original_query="问题",
        current_query="问题",
        kb_evidence=kb_evidence,
        web_evidence=web_evidence,
        article_fulltext_evidence=article_fulltext_evidence,
        web_fulltext_evidence=web_fulltext_evidence,
        allowed_actions=[AgentAction.ANSWER, AgentAction.INSUFFICIENT],
        conversation=[],
    )

    payload = json.loads(client.calls[0][1])
    assert payload["valid_indexes"] == {
        "selected_result_indexes": [0, 1],
        "selected_web_result_indexes": [0, 1, 2],
        "selected_article_content_indexes": [0],
        "selected_web_page_content_indexes": [0, 1, 2, 3],
    }
    assert [item["index"] for item in payload["knowledge_base_evidence"]] == [
        0,
        1,
    ]
    assert [item["index"] for item in payload["web_search_evidence"]] == [
        0,
        1,
        2,
    ]
    assert all(
        "temporary_chunk_indexes" not in item
        for item in (
            payload["knowledge_base_fulltext_evidence"]
            + payload["web_fulltext_evidence"]
        )
    )
    system_prompt = client.calls[0][0]
    assert "四类 index 是彼此独立的局部零基索引" in system_prompt
    assert "不能跨 evidence 类型使用 index" in system_prompt
    assert "必须来自对应 valid_indexes" in system_prompt
    assert "对应 valid_indexes 为空" in system_prompt


@pytest.mark.parametrize(
    "allowed_actions",
    [
        [
            AgentAction.ANSWER,
            AgentAction.REWRITE_QUERY,
            AgentAction.GET_ARTICLE_CONTENT,
            AgentAction.INSUFFICIENT,
        ],
        [AgentAction.REWRITE_QUERY, AgentAction.INSUFFICIENT],
        [
            AgentAction.REWRITE_QUERY,
            AgentAction.WEB_SEARCH,
            AgentAction.INSUFFICIENT,
        ],
        [
            AgentAction.ANSWER,
            AgentAction.GET_ARTICLE_CONTENT,
            AgentAction.INSUFFICIENT,
        ],
        [AgentAction.REWRITE_QUERY, AgentAction.INSUFFICIENT],
        [
            AgentAction.ANSWER,
            AgentAction.REWRITE_QUERY,
            AgentAction.INSUFFICIENT,
        ],
    ],
    ids=[
        "no_web_with_kb",
        "empty_kb",
        "web_allowed_without_results",
        "rewrite_exhausted",
        "web_budget_exhausted",
        "fulltext_unavailable",
    ],
)
def test_decision_response_schema_uses_exact_runtime_allowed_actions(
    allowed_actions: list[AgentAction],
) -> None:
    client = SequencedLLMClient(
        [
            (
                '{"evidence_status":"insufficient","reason":"证据不足",'
                '"next_action":"insufficient","selected_result_indexes":[],'
                '"selected_web_result_indexes":[],'
                '"selected_article_result_index":null,'
                '"selected_web_page_result_index":null,'
                '"selected_article_content_indexes":[],'
                '"selected_web_page_content_indexes":[]}'
            )
        ]
    )

    AgentReasoningService(client).decide(
        original_query="问题",
        current_query="问题",
        kb_evidence=[],
        web_evidence=[],
        article_fulltext_evidence=[],
        web_fulltext_evidence=[],
        allowed_actions=allowed_actions,
        conversation=[],
    )

    assert _next_action_enum(client.response_schemas[0]) == [
        action.value for action in allowed_actions
    ]
    assert AgentAction.KNOWLEDGE_SEARCH.value not in _next_action_enum(
        client.response_schemas[0]
    )
    assert AgentAction.PARTIAL_ANSWER.value not in _next_action_enum(
        client.response_schemas[0]
    )


def test_decision_rejects_action_outside_runtime_allowed_actions() -> None:
    client = SequencedLLMClient(
        [
            (
                '{"evidence_status":"insufficient","reason":"尝试联网",'
                '"next_action":"web_search","selected_result_indexes":[],'
                '"selected_web_result_indexes":[],'
                '"selected_article_result_index":null,'
                '"selected_web_page_result_index":null,'
                '"selected_article_content_indexes":[],'
                '"selected_web_page_content_indexes":[]}'
            )
        ]
    )
    allowed_actions = [
        AgentAction.ANSWER,
        AgentAction.REWRITE_QUERY,
        AgentAction.GET_ARTICLE_CONTENT,
        AgentAction.INSUFFICIENT,
    ]

    with pytest.raises(LLMResponseError, match="Agent 决策结果无效"):
        AgentReasoningService(client).decide(
            original_query="不要联网，根据知识库回答 什么是过拟合？",
            current_query="什么是过拟合？",
            kb_evidence=[
                {
                    "article_id": 11,
                    "chunk_id": 101,
                    "title": "过拟合",
                    "chunk_text": "过拟合是模型记住训练数据噪声。",
                    "score": 0.91,
                }
            ],
            web_evidence=[],
            article_fulltext_evidence=[],
            web_fulltext_evidence=[],
            allowed_actions=allowed_actions,
            conversation=[],
        )

    schema_actions = _next_action_enum(client.response_schemas[0])
    assert schema_actions == [action.value for action in allowed_actions]
    assert AgentAction.WEB_SEARCH.value not in schema_actions
    assert AgentAction.FETCH_WEB_PAGE.value not in schema_actions


def test_reasoning_service_contextualizes_query_with_bounded_history() -> None:
    client = SequencedLLMClient(
        [
            (
                '{"query":"大语言模型训练的第二阶段有监督微调 SFT '
                '主要做了什么？"}'
            )
        ]
    )
    conversation = [
        HumanMessage(content=f"历史问题 {index}")
        if index % 2 == 0
        else AIMessage(content=f"历史回答 {index}")
        for index in range(8)
    ]

    result = AgentReasoningService(client).contextualize_query(
        original_query="那第二阶段主要做了什么？",
        conversation=conversation,
    )

    assert result == "大语言模型训练的第二阶段有监督微调 SFT 主要做了什么？"
    system_prompt, user_prompt = client.calls[0]
    assert "独立可理解的检索 Query" in system_prompt
    assert "不得添加对话历史中不存在的事实" in system_prompt
    assert "不得回答用户问题" in system_prompt
    payload = json.loads(user_prompt)
    assert payload["original_query"] == "那第二阶段主要做了什么？"
    assert [item["content"] for item in payload["recent_conversation"]] == [
        "历史问题 2",
        "历史回答 3",
        "历史问题 4",
        "历史回答 5",
        "历史问题 6",
        "历史回答 7",
    ]
    assert client.response_schemas == [QueryRewriteResult]
    assert client.purposes == ["contextualize"]
    assert client.thinking_overrides == [False]


@pytest.mark.parametrize(
    "raw_result",
    [
        "not-json",
        (
            '{"evidence_status":"sufficient","reason":"足够",'
            '"next_action":"answer","selected_result_indexes":[0],'
            '"unexpected":true}'
        ),
        (
            '{"evidence_status":"partial","reason":"足够",'
            '"next_action":"answer","selected_result_indexes":[-1]}'
        ),
        (
            '{"evidence_status":"partial","reason":"足够",'
            '"next_action":"answer","selected_result_indexes":[true]}'
        ),
        (
            '{"evidence_status":"sufficient","reason":"知识库证据足够",'
            '"next_action":"answer","selected_result_indexes":[],'
            '"reasoning":"旧版推理字段",'
            '"selected_article_indexes":[0]}'
        ),
        (
            '{"evidence_status":"insufficient","reason":"证据不足",'
            '"next_action":"rewrite_query","selected_result_indexes":[],'
            '"selected_web_result_indexes":[],'
            '"selected_article_result_index":null,'
            '"selected_web_page_result_index":null,'
            '"selected_article_content_indexes":[],'
            '"selected_web_page_content_indexes":[],'
            '"rewrite_query":"get_article_content",'
            '"insufficient":"证据不足"}'
        ),
    ],
)
def test_reasoning_service_rejects_malformed_decision(raw_result: str) -> None:
    service = AgentReasoningService(SequencedLLMClient([raw_result]))

    with pytest.raises(LLMResponseError, match="Agent 决策结果无效"):
        service.decide(
            original_query="问题",
            current_query="问题",
                kb_evidence=[],
                web_evidence=[],
                article_fulltext_evidence=[],
                web_fulltext_evidence=[],
            allowed_actions=[AgentAction.INSUFFICIENT],
            conversation=[],
        )


def test_decision_prompt_describes_strict_agent_decision_contract() -> None:
    client = SequencedLLMClient(
        [
            (
                '{"evidence_status":"insufficient","reason":"证据不足",'
                '"next_action":"insufficient","selected_result_indexes":[],'
                '"selected_web_result_indexes":[],'
                '"selected_article_result_index":null,'
                '"selected_web_page_result_index":null,'
                '"selected_article_content_indexes":[],'
                '"selected_web_page_content_indexes":[]}'
            )
        ]
    )
    service = AgentReasoningService(client)

    service.decide(
        original_query="问题",
        current_query="问题",
        kb_evidence=[],
        web_evidence=[],
        article_fulltext_evidence=[],
        web_fulltext_evidence=[],
        allowed_actions=[AgentAction.INSUFFICIENT],
        conversation=[],
    )

    system_prompt = client.calls[0][0]
    required_fragments = [
        '"evidence_status": "sufficient | partial | insufficient"',
        '"reason": "string"',
        '"next_action": "<payload.allowed_actions 中的一个值>"',
        "以下动作规则仅说明动作语义，不表示它们在当前轮可用",
        '"selected_result_indexes": []',
        '"selected_web_result_indexes": []',
        '"selected_article_result_index": null',
        '"selected_web_page_result_index": null',
        '"selected_article_content_indexes": []',
        '"selected_web_page_content_indexes": []',
        "selected_result_indexes 对应 knowledge_base_evidence",
        "selected_web_result_indexes 对应 web_search_evidence",
        "selected_article_result_index 仅用于 get_article_content",
        "selected_web_page_result_index 仅用于 fetch_web_page",
        "selected_article_content_indexes 对应 knowledge_base_fulltext_evidence",
        "selected_web_page_content_indexes 对应 web_fulltext_evidence",
        "所有 index 均从 0 开始",
        "answer：evidence_status 必须为 sufficient 或 partial",
        "rewrite_query：evidence_status 必须为 partial 或 insufficient",
        "web_search：evidence_status 必须为 partial 或 insufficient",
        "insufficient：evidence_status 必须为 insufficient",
        "next_action = answer 时，四个 evidence selection 数组合计至少一个必须非空",
        "合法 answer 示例",
        '"selected_result_indexes": [0]',
        "非法 answer 示例",
        "四个 evidence selection 数组全部为空，因此不得返回 answer",
        "没有任何真实 evidence 可以选择时，不得返回 answer",
        "必须从 payload.allowed_actions 中选择其他合法动作",
        "不得伪造 evidence index",
        "最终 JSON 对象必须且只能包含以下九个固定顶层字段",
        "无论选择什么 action，这九个字段都必须全部出现",
        "每次输出都必须保持完全相同的字段集合，只改变字段值",
        "Action 名称只能作为 next_action 字段的值出现",
        "rewrite_query 绝不能作为 JSON 顶层字段",
        "insufficient 绝不能作为 JSON 顶层字段",
        "合法 rewrite_query 示例",
        "合法 insufficient 示例",
        (
            "非法顶层字段：reasoning、rewrite_query、web_search、"
            "get_article_content、fetch_web_page、answer、insufficient、"
            "selected_article_indexes、selected_web_page_indexes、"
            "selected_knowledge_base_fulltext_indexes、"
            "selected_web_fulltext_indexes"
        ),
        "reasoning",
        "selected_article_indexes",
        "selected_web_page_indexes",
        "selected_knowledge_base_fulltext_indexes",
        "selected_web_fulltext_indexes",
    ]
    for fragment in required_fragments:
        assert fragment in system_prompt

    decision_fields = [
        "evidence_status",
        "reason",
        "next_action",
        "selected_result_indexes",
        "selected_web_result_indexes",
        "selected_article_result_index",
        "selected_web_page_result_index",
        "selected_article_content_indexes",
        "selected_web_page_content_indexes",
    ]
    rewrite_example = system_prompt.split("合法 rewrite_query 示例：", 1)[1].split(
        "合法 insufficient 示例：",
        1,
    )[0]
    insufficient_example = system_prompt.split("合法 insufficient 示例：", 1)[1].split(
        "answer 证据选择硬规则：",
        1,
    )[0]
    for field in decision_fields:
        assert f'"{field}"' in rewrite_example
        assert f'"{field}"' in insufficient_example


def test_answer_prompt_requires_grounding_and_bounds_conversation() -> None:
    client = SequencedLLMClient(["{\"answer\":\"证据支持的回答\"}"])
    service = AgentReasoningService(client)
    evidence = [
        {
            "article_id": 11,
            "chunk_id": 101,
            "title": "选中证据",
            "chunk_text": "只允许使用这一段。",
            "score": 0.91,
        }
    ]
    messages = [HumanMessage(content=f"历史消息 {index}") for index in range(8)]

    service.generate_answer(
        original_query="问题",
        evidence=evidence,
        evidence_status=EvidenceStatus.SUFFICIENT,
        conversation=messages,
    )

    system_prompt, user_prompt = client.calls[0]
    payload = json.loads(user_prompt)
    assert "只能使用 evidence 中的内容" in system_prompt
    assert "不得使用模型自身知识" in system_prompt
    assert "搜索结果摘要" in system_prompt
    assert "不得声称阅读网页全文" in system_prompt
    assert payload["evidence"] == evidence
    assert [item["content"] for item in payload["recent_conversation"]] == [
        "历史消息 2",
        "历史消息 3",
        "历史消息 4",
        "历史消息 5",
        "历史消息 6",
        "历史消息 7",
    ]
