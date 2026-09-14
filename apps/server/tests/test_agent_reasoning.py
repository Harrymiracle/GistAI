import json

import pytest
from langchain_core.messages import HumanMessage

from app.agent.reasoning import AgentReasoningService
from app.agent.schemas import AgentAction, EvidenceStatus
from app.ai.errors import LLMResponseError


class SequencedLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return next(self._responses)


def test_reasoning_service_parses_decision_rewrite_and_answer() -> None:
    client = SequencedLLMClient(
        [
            (
                '{"evidence_status":"partial","reason":"仅支持定义部分",'
                '"next_action":"answer","selected_result_indexes":[0],'
                '"selected_web_result_indexes":[0]}'
            ),
            '{"query":"Agent Memory 的工作机制"}',
            '{"answer":"Agent Memory 会保存对话上下文。"}',
        ]
    )
    service = AgentReasoningService(client)
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

    assert decision.evidence_status is EvidenceStatus.PARTIAL
    assert decision.next_action is AgentAction.ANSWER
    assert decision.selected_result_indexes == [0]
    assert decision.selected_web_result_indexes == [0]
    decision_payload = json.loads(client.calls[0][1])
    assert decision_payload["knowledge_base_evidence"][0]["index"] == 0
    assert decision_payload["web_search_evidence"][0]["index"] == 0
    assert rewritten == "Agent Memory 的工作机制"
    assert answer == "Agent Memory 会保存对话上下文。"
    assert len(client.calls) == 3


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
