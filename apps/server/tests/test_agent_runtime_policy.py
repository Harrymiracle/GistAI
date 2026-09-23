from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.nodes import (
    evaluate_and_decide,
    get_article_content,
    initialize,
    knowledge_search,
)
from app.agent.policy import AgentLimits, AgentRuntimePolicy
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentErrorType,
    ArticleContentResult,
    EvidenceStatus,
    IntentDecision,
    KnowledgeSearchResult,
    ToolExecutionStatus,
)


class KnowledgeSearchStub:
    def __init__(
        self,
        results: list[KnowledgeSearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls = 0

    def search(self, _payload: object) -> list[KnowledgeSearchResult]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.results


class NoWebSearchStub:
    def search(self, _query: str) -> list[object]:
        raise AssertionError("当前测试不应调用 Web Search")


class NoReasoningStub:
    def classify_intent(self, **_options: object) -> IntentDecision:
        raise AssertionError("当前测试不应调用意图判断")

    def decide(self, **_options: object) -> AgentDecision:
        raise AssertionError("当前测试不应调用决策")

    def rewrite_query(self, **_options: object) -> str:
        raise AssertionError("当前测试不应调用查询改写")

    def generate_answer(self, **_options: object) -> str:
        raise AssertionError("当前测试不应生成回答")


class ArticleContentStub:
    def get(self, article_id: int) -> ArticleContentResult:
        return ArticleContentResult(
            article_id=article_id,
            title="测试文章",
            clean_content="可用正文",
        )


class BrokenFulltextSelector:
    def select(self, **_options: object) -> tuple[list[object], list[object]]:
        raise RuntimeError("internal-db-url=secret")


def _runtime(search: KnowledgeSearchStub) -> Runtime[AgentContext]:
    return Runtime(
        context=AgentContext(
            knowledge_search=search,
            web_search=NoWebSearchStub(),
            reasoning=NoReasoningStub(),
        )
    )


def _state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "allow_web": True,
        "requires_freshness": False,
        "kb_results": [],
        "web_results": [],
        "article_fulltext_evidence": [],
        "web_fulltext_evidence": [],
        "selected_evidence": [],
        "evidence_status": EvidenceStatus.UNKNOWN,
        "rewrite_count": 0,
        "step_count": 0,
        "tool_call_counts": {},
        "read_article_ids": [],
        "fetched_web_urls": [],
        "last_error_type": None,
    }
    state.update(overrides)
    return state


def test_policy_computes_actions_from_state_and_limits() -> None:
    policy = AgentRuntimePolicy()
    state = _state(
        kb_results=[{"article_id": 11}],
        web_results=[{"url": "https://example.com/a"}],
    )

    outcome = policy.evaluate(state)

    assert outcome.allowed_actions == [
        AgentAction.ANSWER,
        AgentAction.REWRITE_QUERY,
        AgentAction.WEB_SEARCH,
        AgentAction.GET_ARTICLE_CONTENT,
        AgentAction.FETCH_WEB_PAGE,
        AgentAction.INSUFFICIENT,
    ]
    assert outcome.should_terminate is False


def test_each_exhausted_budget_removes_only_its_action() -> None:
    policy = AgentRuntimePolicy()
    state = _state(
        kb_results=[{"article_id": 11}, {"article_id": 12}],
        web_results=[
            {"url": "https://example.com/a"},
            {"url": "https://example.com/b"},
        ],
        rewrite_count=1,
        tool_call_counts={
            "knowledge_search": 2,
            "web_search": 1,
            "get_article_content": 2,
            "fetch_web_page": 2,
        },
    )

    outcome = policy.evaluate(state)

    assert outcome.allowed_actions == [
        AgentAction.ANSWER,
        AgentAction.INSUFFICIENT,
    ]


def test_global_step_limit_blocks_progress_but_keeps_answer_termination() -> None:
    policy = AgentRuntimePolicy()
    state = _state(
        kb_results=[{"article_id": 11}],
        step_count=8,
    )

    outcome = policy.evaluate(state)

    assert outcome.allowed_actions == [
        AgentAction.ANSWER,
        AgentAction.INSUFFICIENT,
    ]
    assert not {
        AgentAction.KNOWLEDGE_SEARCH,
        AgentAction.REWRITE_QUERY,
        AgentAction.WEB_SEARCH,
        AgentAction.GET_ARTICLE_CONTENT,
        AgentAction.FETCH_WEB_PAGE,
    }.intersection(outcome.allowed_actions)


def test_max_steps_with_preselected_evidence_terminates_as_partial() -> None:
    update = evaluate_and_decide(
        {
            **_state(
                allow_web=False,
                step_count=8,
                selected_evidence=[
                    {
                        "source_type": "knowledge_base",
                        "article_id": 11,
                        "chunk_id": 101,
                        "chunk_text": "仅支持部分结论的证据",
                    }
                ],
            ),
            "original_query": "复合问题",
            "current_query": "复合问题",
            "messages": [HumanMessage(content="复合问题")],
        },
        _runtime(KnowledgeSearchStub()),
    )

    assert update["next_action"] is AgentAction.PARTIAL_ANSWER
    assert update["evidence_status"] is EvidenceStatus.PARTIAL
    assert update["selected_evidence"]


def test_max_steps_without_evidence_terminates_without_reasoning() -> None:
    update = evaluate_and_decide(
        {
            **_state(allow_web=False, step_count=8),
            "original_query": "未知问题",
            "current_query": "未知问题",
            "messages": [HumanMessage(content="未知问题")],
        },
        _runtime(KnowledgeSearchStub()),
    )

    assert update["allowed_actions"] == []
    assert update["next_action"] is AgentAction.INSUFFICIENT
    assert update["selected_evidence"] == []
    assert update["evidence_status"] is EvidenceStatus.INSUFFICIENT


def test_no_actions_terminates_partial_only_with_selected_evidence() -> None:
    policy = AgentRuntimePolicy()

    partial = policy.terminate(
        _state(
            selected_evidence=[{"source_type": "knowledge_base", "chunk_id": 1}],
            evidence_status=EvidenceStatus.PARTIAL,
        ),
        "没有合法动作",
    )
    insufficient = policy.terminate(_state(), "没有合法动作")

    assert partial.termination_action is AgentAction.PARTIAL_ANSWER
    assert insufficient.termination_action is AgentAction.INSUFFICIENT


def test_execution_error_disables_progress_and_preserves_safe_answer_path() -> None:
    policy = AgentRuntimePolicy()
    state = _state(
        kb_results=[{"article_id": 11}],
        last_error_type=AgentErrorType.EXECUTION,
    )

    outcome = policy.evaluate(state)

    assert outcome.allowed_actions == [
        AgentAction.ANSWER,
        AgentAction.INSUFFICIENT,
    ]


def test_freshness_requires_web_evidence_before_answer_is_allowed() -> None:
    policy = AgentRuntimePolicy()
    without_web = policy.evaluate(
        _state(
            requires_freshness=True,
            kb_results=[{"article_id": 11}],
        )
    )
    with_web = policy.evaluate(
        _state(
            requires_freshness=True,
            kb_results=[{"article_id": 11}],
            web_results=[{"url": "https://example.com/a"}],
        )
    )

    assert AgentAction.ANSWER not in without_web.allowed_actions
    assert AgentAction.ANSWER in with_web.allowed_actions


def _should_force_web(
    policy: AgentRuntimePolicy,
    state: dict[str, object],
) -> bool:
    predicate = getattr(policy, "should_force_web_for_freshness", None)
    assert callable(predicate)
    return predicate(state)


def test_freshness_forces_first_web_search_when_budget_is_available() -> None:
    policy = AgentRuntimePolicy()

    assert _should_force_web(
        policy,
        _state(requires_freshness=True, allow_web=True),
    ) is True


def test_freshness_does_not_force_web_after_web_evidence_exists() -> None:
    policy = AgentRuntimePolicy()

    assert _should_force_web(
        policy,
        _state(
            requires_freshness=True,
            allow_web=True,
            web_results=[{"url": "https://example.com/current"}],
        ),
    ) is False


def test_freshness_does_not_force_web_after_search_budget_is_exhausted() -> None:
    policy = AgentRuntimePolicy()

    assert _should_force_web(
        policy,
        _state(
            requires_freshness=True,
            allow_web=True,
            tool_call_counts={"web_search": 1},
        ),
    ) is False


def test_freshness_does_not_force_web_when_web_is_disabled() -> None:
    policy = AgentRuntimePolicy()

    assert _should_force_web(
        policy,
        _state(requires_freshness=True, allow_web=False),
    ) is False


def test_freshness_does_not_force_web_after_terminal_error() -> None:
    policy = AgentRuntimePolicy()

    assert _should_force_web(
        policy,
        _state(
            requires_freshness=True,
            allow_web=True,
            last_error_type=AgentErrorType.EXECUTION,
        ),
    ) is False


def test_freshness_does_not_force_web_at_step_limit() -> None:
    policy = AgentRuntimePolicy()

    assert _should_force_web(
        policy,
        _state(
            requires_freshness=True,
            allow_web=True,
            step_count=policy.limits.max_steps,
        ),
    ) is False


def test_disallowing_web_removes_and_blocks_web_search() -> None:
    policy = AgentRuntimePolicy()
    state = _state(allow_web=False)

    outcome = policy.evaluate(state)

    assert AgentAction.WEB_SEARCH not in outcome.allowed_actions
    assert policy.can_execute(state, AgentAction.WEB_SEARCH) is False


def test_freshness_without_web_permission_cannot_answer_from_kb() -> None:
    policy = AgentRuntimePolicy()
    state = _state(
        allow_web=False,
        requires_freshness=True,
        kb_results=[{"article_id": 11}],
    )

    outcome = policy.evaluate(state)

    assert AgentAction.ANSWER not in outcome.allowed_actions
    assert AgentAction.WEB_SEARCH not in outcome.allowed_actions


def test_limits_cover_worst_case_legal_path_exactly() -> None:
    limits = AgentLimits()

    assert limits.max_kb_searches == 2
    assert limits.max_rewrites == 1
    assert limits.max_web_searches == 1
    assert limits.max_article_reads == 2
    assert limits.max_web_page_reads == 2
    assert limits.max_steps == 8


def test_kb_budget_rejection_does_not_increment_step_or_tool_count() -> None:
    search = KnowledgeSearchStub()

    update = knowledge_search(
        {
            "current_query": "预算测试",
            "step_count": 2,
            "tool_call_counts": {"knowledge_search": 2},
        },
        _runtime(search),
    )

    assert search.calls == 0
    assert update["step_count"] == 2
    assert update["tool_call_counts"] == {"knowledge_search": 2}
    assert update["last_error_type"] is AgentErrorType.POLICY
    assert update["last_tool_result"]["status"] == ToolExecutionStatus.VALIDATION_ERROR


def test_invalid_kb_payload_is_rejected_before_tool_attempt() -> None:
    search = KnowledgeSearchStub()

    update = knowledge_search(
        {
            "current_query": " " * 3,
            "step_count": 0,
            "tool_call_counts": {},
        },
        _runtime(search),
    )

    assert search.calls == 0
    assert update["step_count"] == 0
    assert update["tool_call_counts"] == {}
    assert update["last_error_type"] is AgentErrorType.POLICY
    assert update["last_tool_result"]["status"] == ToolExecutionStatus.VALIDATION_ERROR


def test_kb_execution_error_counts_attempt_and_uses_safe_classification() -> None:
    search = KnowledgeSearchStub(error=TimeoutError("api_key=secret"))

    update = knowledge_search(
        {
            "current_query": "错误测试",
            "step_count": 0,
            "tool_call_counts": {},
        },
        _runtime(search),
    )

    assert search.calls == 1
    assert update["step_count"] == 1
    assert update["tool_call_counts"] == {"knowledge_search": 1}
    assert update["last_error_type"] is AgentErrorType.EXECUTION
    assert update["last_tool_result"]["status"] == ToolExecutionStatus.EXECUTION_ERROR
    assert "secret" not in update["last_tool_error"]


def test_kb_empty_result_is_a_successful_attempt_not_an_error() -> None:
    update = knowledge_search(
        {
            "current_query": "空结果测试",
            "step_count": 0,
            "tool_call_counts": {},
        },
        _runtime(KnowledgeSearchStub()),
    )

    assert update["step_count"] == 1
    assert update["tool_call_counts"] == {"knowledge_search": 1}
    assert update["last_error_type"] is None
    assert update["last_tool_result"]["status"] == ToolExecutionStatus.EMPTY


def test_article_postprocessing_error_is_safely_normalized() -> None:
    context = AgentContext(
        knowledge_search=KnowledgeSearchStub(),
        web_search=NoWebSearchStub(),
        reasoning=NoReasoningStub(),
        article_content=ArticleContentStub(),
        fulltext_selector=BrokenFulltextSelector(),  # type: ignore[arg-type]
    )

    update = get_article_content(
        {
            **_state(kb_results=[{"article_id": 11}]),
            "current_query": "问题",
            "selected_article_result_index": 0,
        },
        Runtime(context=context),
    )

    assert update["step_count"] == 1
    assert update["tool_call_counts"] == {"get_article_content": 1}
    assert update["last_error_type"] is AgentErrorType.EXECUTION
    assert update["last_tool_result"]["status"] == ToolExecutionStatus.EXECUTION_ERROR
    assert "secret" not in update["last_tool_error"]


def test_initialize_resets_all_runtime_policy_fields_and_keeps_messages() -> None:
    messages = [HumanMessage(content="新问题")]

    update = initialize(
        {
            "messages": messages,
            "step_count": 8,
            "tool_call_counts": {"knowledge_search": 2},
            "last_error_type": AgentErrorType.EXECUTION,
            "last_tool_result": {"tool_name": "knowledge_search"},
            "action_history": [{"action": "knowledge_search"}],
        }
    )

    assert "messages" not in update
    assert update["step_count"] == 0
    assert update["tool_call_counts"] == {}
    assert update["last_error_type"] is None
    assert update["last_tool_result"] is None
    assert update["action_history"] == []
