from collections.abc import Sequence
from uuid import uuid4

from langchain_core.messages import BaseMessage

from app.agent.context import AgentContext
from app.agent.fulltext import FullTextEvidenceSelector
from app.agent.graph import create_agent_graph
from app.agent.schemas import (
    AgentAction,
    AgentDecision,
    AgentIntent,
    ArticleContentResult,
    EvidenceStatus,
    IntentDecision,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
    WebPageContentResult,
    WebSearchResult,
)
from app.agent.web_page_fetch import WebPageValidationError
from app.embedding.chunker import TokenChunker


class KnowledgeSearchStub:
    def __init__(self, article_ids: list[int]) -> None:
        self.article_ids = article_ids

    def search(self, _payload: KnowledgeSearchInput) -> list[KnowledgeSearchResult]:
        return [
            KnowledgeSearchResult(
                article_id=article_id,
                chunk_id=100 + index,
                title=f"文章 {article_id}",
                chunk_text="相关但不完整的片段",
                score=0.8,
            )
            for index, article_id in enumerate(self.article_ids)
        ]


class WebSearchStub:
    def __init__(self, results: list[WebSearchResult] | None = None) -> None:
        self.results = results or []
        self.calls = 0

    def search(self, _query: str) -> list[WebSearchResult]:
        self.calls += 1
        return self.results


class ArticleContentStub:
    def __init__(
        self,
        unavailable_ids: set[int] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.unavailable_ids = unavailable_ids or set()
        self.error = error
        self.calls: list[int] = []

    def get(self, article_id: int) -> ArticleContentResult | None:
        self.calls.append(article_id)
        if self.error:
            raise self.error
        if article_id in self.unavailable_ids:
            return None
        return ArticleContentResult(
            article_id=article_id,
            title=f"文章 {article_id}",
            clean_content=f"文章 {article_id} 的完整正文包含目标答案。" * 20,
        )


class WebPageFetchStub:
    def __init__(
        self,
        error: Exception | None = None,
        result: WebPageContentResult | None = None,
    ) -> None:
        self.error = error
        self.result = result
        self.calls: list[str] = []

    def fetch(self, url: str) -> WebPageContentResult:
        self.calls.append(url)
        if self.error:
            raise self.error
        return self.result or WebPageContentResult(
            url=url,
            title="网页标题",
            clean_content="网页完整正文包含最新目标答案。" * 20,
            source="示例站点",
        )


class ScriptedReasoning:
    def __init__(
        self,
        decisions: list[AgentDecision],
        *,
        fresh: bool = False,
        rewrites: list[str] | None = None,
    ) -> None:
        self.decisions = decisions
        self.fresh = fresh
        self.rewrites = list(rewrites or [])
        self.decision_inputs: list[dict[str, object]] = []
        self.answer_evidence: list[dict[str, object]] = []

    def classify_intent(
        self, *, query: str, conversation: Sequence[BaseMessage]
    ) -> IntentDecision:
        del query, conversation
        return IntentDecision(
            intent=AgentIntent.FRESH_INFORMATION if self.fresh else AgentIntent.OPEN,
            allow_web=True,
            requires_freshness=self.fresh,
            reason="测试意图",
        )

    def decide(self, **options: object) -> AgentDecision:
        self.decision_inputs.append(options)
        return self.decisions.pop(0)

    def rewrite_query(self, **_options: object) -> str:
        if not self.rewrites:
            raise AssertionError("当前测试不应改写")
        return self.rewrites.pop(0)

    def generate_answer(self, **options: object) -> str:
        self.answer_evidence = list(options["evidence"])  # type: ignore[arg-type]
        return "基于全文证据的回答"


def _decision(action: AgentAction, **options: object) -> AgentDecision:
    status = (
        EvidenceStatus.SUFFICIENT
        if action is AgentAction.ANSWER
        else EvidenceStatus.PARTIAL
    )
    return AgentDecision(
        evidence_status=status,
        reason="测试决策",
        next_action=action,
        **options,
    )


def _invoke(
    *,
    knowledge_ids: list[int],
    reasoning: ScriptedReasoning,
    articles: ArticleContentStub | None = None,
    web_search: WebSearchStub | None = None,
    web_fetch: WebPageFetchStub | None = None,
    graph=None,
    thread_id: str | None = None,
):
    article_service = articles or ArticleContentStub()
    web_search_service = web_search or WebSearchStub()
    web_fetch_service = web_fetch or WebPageFetchStub()
    context = AgentContext(
        knowledge_search=KnowledgeSearchStub(knowledge_ids),
        web_search=web_search_service,
        article_content=article_service,
        web_page_fetch=web_fetch_service,
        fulltext_selector=FullTextEvidenceSelector(
            chunker=TokenChunker(chunk_size=40, overlap=0),
            max_context_tokens=120,
        ),
        reasoning=reasoning,
    )
    result = (graph or create_agent_graph()).invoke(
        {"messages": [{"role": "user", "content": "目标答案是什么？"}]},
        config={"configurable": {"thread_id": thread_id or str(uuid4())}},
        context=context,
    )
    return result, article_service, web_search_service, web_fetch_service


def test_kb_chunk_sufficient_does_not_read_article() -> None:
    reasoning = ScriptedReasoning(
        [_decision(AgentAction.ANSWER, selected_result_indexes=[0])]
    )

    result, articles, _, _ = _invoke(knowledge_ids=[1], reasoning=reasoning)

    assert result["final_answer"] == "基于全文证据的回答"
    assert articles.calls == []


def test_incomplete_kb_chunk_reads_article_then_answers_from_fulltext() -> None:
    reasoning = ScriptedReasoning(
        [
            _decision(
                AgentAction.GET_ARTICLE_CONTENT,
                selected_article_result_index=0,
            ),
            _decision(
                AgentAction.ANSWER,
                selected_article_content_indexes=[0],
            ),
        ]
    )

    result, articles, _, _ = _invoke(knowledge_ids=[7], reasoning=reasoning)

    assert articles.calls == [7]
    assert result["tool_call_counts"]["get_article_content"] == 1
    assert result["article_contents"] == []
    fulltext_context = reasoning.decision_inputs[1]["article_fulltext_evidence"]
    assert isinstance(fulltext_context, list)
    assert sum(item["token_count"] for item in fulltext_context) <= 120
    assert sum(len(item["content"]) for item in fulltext_context) < len(
        "目标答案正文。" * 20
    )
    assert reasoning.answer_evidence[0]["source_type"] == "knowledge_base_fulltext"
    assert result["sources"] == [{"article_id": 7, "title": "文章 7"}]
    assert [
        item.get("enable_thinking", "missing")
        for item in reasoning.decision_inputs
    ] == ["missing", False]


def test_unavailable_article_is_safe_and_does_not_leak_owner() -> None:
    reasoning = ScriptedReasoning(
        [
            _decision(
                AgentAction.GET_ARTICLE_CONTENT,
                selected_article_result_index=0,
            ),
            _decision(AgentAction.INSUFFICIENT),
        ]
    )
    articles = ArticleContentStub(unavailable_ids={9})

    result, _, _, _ = _invoke(
        knowledge_ids=[9], reasoning=reasoning, articles=articles
    )

    assert result["article_contents"] == []
    assert "其他用户" not in result["final_answer"]
    assert result["tool_call_counts"]["get_article_content"] == 1


def test_article_read_execution_error_counts_once_and_hides_details() -> None:
    reasoning = ScriptedReasoning(
        [
            _decision(
                AgentAction.GET_ARTICLE_CONTENT,
                selected_article_result_index=0,
            )
        ]
    )
    articles = ArticleContentStub(error=RuntimeError("数据库连接详情"))

    result, _, _, _ = _invoke(
        knowledge_ids=[9], reasoning=reasoning, articles=articles
    )

    assert articles.calls == [9]
    assert result["tool_call_counts"]["get_article_content"] == 1
    assert "数据库连接详情" not in result["last_tool_error"]
    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT


def test_illegal_article_index_is_rejected_before_service_call() -> None:
    reasoning = ScriptedReasoning(
        [
            _decision(
                AgentAction.GET_ARTICLE_CONTENT,
                selected_article_result_index=10,
            )
        ]
    )

    result, articles, _, _ = _invoke(knowledge_ids=[1], reasoning=reasoning)

    assert articles.calls == []
    assert "get_article_content" not in result["tool_call_counts"]
    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT


def test_article_read_rejects_sufficient_evidence_status() -> None:
    reasoning = ScriptedReasoning(
        [
            AgentDecision(
                evidence_status=EvidenceStatus.SUFFICIENT,
                reason="证据已足够却仍要求读取",
                next_action=AgentAction.GET_ARTICLE_CONTENT,
                selected_article_result_index=0,
            )
        ]
    )

    result, articles, _, _ = _invoke(knowledge_ids=[1], reasoning=reasoning)

    assert articles.calls == []
    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT


def test_article_read_budget_blocks_third_read() -> None:
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=0),
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=1),
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=2),
        ]
    )

    result, articles, _, _ = _invoke(
        knowledge_ids=[1, 2, 3], reasoning=reasoning
    )

    assert articles.calls == [1, 2]
    assert result["tool_call_counts"]["get_article_content"] == 2
    assert AgentAction.GET_ARTICLE_CONTENT not in result["allowed_actions"]


def test_same_article_is_not_read_twice() -> None:
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=0),
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=0),
        ]
    )

    result, articles, _, _ = _invoke(knowledge_ids=[1], reasoning=reasoning)

    assert articles.calls == [1]
    assert result["tool_call_counts"]["get_article_content"] == 1


def test_web_snippet_sufficient_does_not_fetch_page() -> None:
    web_result = WebSearchResult(
        title="搜索结果",
        url="https://public.example/page",
        snippet="足够支持简单事实的摘要",
        source="示例站点",
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.ANSWER, selected_web_result_indexes=[0]),
        ]
    )

    _, _, _, fetcher = _invoke(
        knowledge_ids=[], reasoning=reasoning, web_search=WebSearchStub([web_result])
    )

    assert fetcher.calls == []


def test_web_snippet_fetches_page_then_answers_from_fulltext() -> None:
    web_result = WebSearchResult(
        title="搜索结果",
        url="https://public.example/page",
        snippet="摘要不完整",
        source="示例站点",
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
            _decision(AgentAction.ANSWER, selected_web_page_content_indexes=[0]),
        ],
        fresh=True,
    )

    result, _, _, fetcher = _invoke(
        knowledge_ids=[], reasoning=reasoning, web_search=WebSearchStub([web_result])
    )

    assert [
        item.get("enable_thinking", "missing")
        for item in reasoning.decision_inputs
    ] == ["missing", "missing", False]

    assert fetcher.calls == ["https://public.example/page"]
    assert result["tool_call_counts"]["fetch_web_page"] == 1
    assert reasoning.answer_evidence[0]["source_type"] == "web_fulltext"
    assert result["sources"][0]["source_type"] == "web"


def test_fetched_page_uses_search_metadata_when_extractor_has_none() -> None:
    web_result = WebSearchResult(
        title="搜索标题",
        url="https://public.example/page",
        snippet="摘要不完整",
        source="搜索来源",
        published_at="2026-09-14",
    )
    fetcher = WebPageFetchStub(
        result=WebPageContentResult(
            url="https://public.example/page",
            title=None,
            clean_content="目标答案正文。" * 20,
            source=None,
        )
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
            _decision(AgentAction.ANSWER, selected_web_page_content_indexes=[0]),
        ]
    )

    result, _, _, _ = _invoke(
        knowledge_ids=[],
        reasoning=reasoning,
        web_search=WebSearchStub([web_result]),
        web_fetch=fetcher,
    )

    assert result["web_page_contents"] == []
    assert result["web_fulltext_evidence"][0]["title"] == "搜索标题"
    assert result["web_fulltext_evidence"][0]["source"] == "搜索来源"
    assert result["web_fulltext_evidence"][0]["published_at"] == (
        "2026-09-14T00:00:00"
    )


def test_illegal_web_index_is_rejected_before_fetch() -> None:
    web_result = WebSearchResult(
        title="搜索结果",
        url="https://public.example/page",
        snippet="摘要",
        source="示例站点",
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=2),
        ]
    )

    result, _, _, fetcher = _invoke(
        knowledge_ids=[], reasoning=reasoning, web_search=WebSearchStub([web_result])
    )

    assert fetcher.calls == []
    assert "fetch_web_page" not in result["tool_call_counts"]


def test_out_of_range_web_fulltext_index_is_rejected_with_range_log(
    caplog,
) -> None:
    web_result = WebSearchResult(
        title="搜索结果",
        url="https://public.example/page",
        snippet="摘要不完整",
        source="示例站点",
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
            _decision(
                AgentAction.ANSWER,
                selected_web_page_content_indexes=[1],
            ),
        ]
    )

    result, _, _, _ = _invoke(
        knowledge_ids=[],
        reasoning=reasoning,
        web_search=WebSearchStub([web_result]),
    )

    assert result["next_action"] is AgentAction.INSUFFICIENT
    assert "field=selected_web_page_content_indexes" in caplog.text
    assert "indexes=[1]" in caplog.text
    assert "candidate_count=1" in caplog.text
    assert "valid_indexes=[0]" in caplog.text


def test_web_page_read_budget_blocks_third_fetch() -> None:
    results = [
        WebSearchResult(
            title=f"搜索结果 {index}",
            url=f"https://public.example/page-{index}",
            snippet="摘要不完整",
            source="示例站点",
        )
        for index in range(3)
    ]
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=1),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=2),
        ]
    )

    result, _, _, fetcher = _invoke(
        knowledge_ids=[], reasoning=reasoning, web_search=WebSearchStub(results)
    )

    assert fetcher.calls == [
        "https://public.example/page-0",
        "https://public.example/page-1",
    ]
    assert result["tool_call_counts"]["fetch_web_page"] == 2
    assert AgentAction.FETCH_WEB_PAGE not in result["allowed_actions"]


def test_same_web_page_is_not_fetched_twice() -> None:
    results = [
        WebSearchResult(
            title=f"搜索结果 {index}",
            url=f"https://public.example/page-{index}",
            snippet="摘要不完整",
            source="示例站点",
        )
        for index in range(2)
    ]
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
        ]
    )

    result, _, _, fetcher = _invoke(
        knowledge_ids=[], reasoning=reasoning, web_search=WebSearchStub(results)
    )

    assert fetcher.calls == ["https://public.example/page-0"]
    assert result["tool_call_counts"]["fetch_web_page"] == 1


def test_ssrf_validation_error_does_not_count_as_real_fetch() -> None:
    web_result = WebSearchResult(
        title="危险结果",
        url="http://127.0.0.1/admin",
        snippet="摘要",
        source="未知",
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
        ]
    )
    fetcher = WebPageFetchStub(WebPageValidationError("禁止访问内部网络"))

    result, _, _, _ = _invoke(
        knowledge_ids=[],
        reasoning=reasoning,
        web_search=WebSearchStub([web_result]),
        web_fetch=fetcher,
    )

    assert fetcher.calls == ["http://127.0.0.1/admin"]
    assert "fetch_web_page" not in result["tool_call_counts"]
    assert "127.0.0.1" not in result["final_answer"]


def test_fetch_execution_error_counts_once_and_stops() -> None:
    web_result = WebSearchResult(
        title="搜索结果",
        url="https://public.example/page",
        snippet="摘要",
        source="示例站点",
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
        ]
    )
    fetcher = WebPageFetchStub(RuntimeError("内部连接细节"))

    result, _, _, _ = _invoke(
        knowledge_ids=[],
        reasoning=reasoning,
        web_search=WebSearchStub([web_result]),
        web_fetch=fetcher,
    )

    assert result["tool_call_counts"]["fetch_web_page"] == 1
    assert "内部连接细节" not in result["last_tool_error"]
    assert result["evidence_status"] is EvidenceStatus.INSUFFICIENT


def test_new_run_resets_fulltext_state_and_read_budgets() -> None:
    graph = create_agent_graph()
    thread_id = str(uuid4())
    first_reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=0),
            _decision(AgentAction.ANSWER, selected_article_content_indexes=[0]),
        ]
    )
    first, _, _, _ = _invoke(
        knowledge_ids=[1],
        reasoning=first_reasoning,
        graph=graph,
        thread_id=thread_id,
    )
    second_reasoning = ScriptedReasoning(
        [_decision(AgentAction.ANSWER, selected_result_indexes=[0])]
    )
    second, _, _, _ = _invoke(
        knowledge_ids=[2],
        reasoning=second_reasoning,
        graph=graph,
        thread_id=thread_id,
    )

    assert first["article_contents"] == []
    assert second["article_contents"] == []
    assert second["web_page_contents"] == []
    assert second["tool_call_counts"] == {"knowledge_search": 1}
    assert len(second["messages"]) == 4


def test_checkpoints_never_store_raw_full_content_or_runtime_dependencies() -> None:
    graph = create_agent_graph()
    thread_id = str(uuid4())
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=0),
            _decision(AgentAction.ANSWER, selected_article_content_indexes=[0]),
        ]
    )

    result, _, _, _ = _invoke(
        knowledge_ids=[1],
        reasoning=reasoning,
        graph=graph,
        thread_id=thread_id,
    )
    history = list(
        graph.get_state_history({"configurable": {"thread_id": thread_id}})
    )

    assert result["article_fulltext_evidence"]
    assert all(
        snapshot.values.get("article_contents", []) == [] for snapshot in history
    )
    assert all(
        snapshot.values.get("web_page_contents", []) == [] for snapshot in history
    )
    assert all("context" not in snapshot.values for snapshot in history)


def test_checkpoints_never_store_raw_web_page_content() -> None:
    graph = create_agent_graph()
    thread_id = str(uuid4())
    web_result = WebSearchResult(
        title="外部资料",
        url="https://public.example/page",
        snippet="摘要不完整",
        source="示例站点",
    )
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
            _decision(AgentAction.ANSWER, selected_web_page_content_indexes=[0]),
        ],
        fresh=True,
    )

    result, _, _, _ = _invoke(
        knowledge_ids=[],
        reasoning=reasoning,
        web_search=WebSearchStub([web_result]),
        graph=graph,
        thread_id=thread_id,
    )
    history = list(
        graph.get_state_history({"configurable": {"thread_id": thread_id}})
    )

    assert result["web_fulltext_evidence"]
    assert all(
        snapshot.values.get("web_page_contents", []) == [] for snapshot in history
    )


def test_worst_case_legal_path_uses_eight_steps_and_always_terminates() -> None:
    web_results = [
        WebSearchResult(
            title=f"搜索结果 {index}",
            url=f"https://public.example/page-{index}",
            snippet="摘要不完整",
            source="示例站点",
        )
        for index in range(2)
    ]
    reasoning = ScriptedReasoning(
        [
            _decision(AgentAction.REWRITE_QUERY),
            _decision(AgentAction.WEB_SEARCH),
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=0),
            _decision(AgentAction.GET_ARTICLE_CONTENT, selected_article_result_index=1),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=0),
            _decision(AgentAction.FETCH_WEB_PAGE, selected_web_page_result_index=1),
            _decision(AgentAction.INSUFFICIENT),
        ],
        rewrites=["更精确的目标答案"],
    )

    result, articles, web_search, fetcher = _invoke(
        knowledge_ids=[1, 2],
        reasoning=reasoning,
        web_search=WebSearchStub(web_results),
    )

    assert result["step_count"] == 8
    assert result["tool_call_counts"] == {
        "knowledge_search": 2,
        "web_search": 1,
        "get_article_content": 2,
        "fetch_web_page": 2,
    }
    assert articles.calls == [1, 2]
    assert web_search.calls == 1
    assert fetcher.calls == [
        "https://public.example/page-0",
        "https://public.example/page-1",
    ]
    assert reasoning.decision_inputs[-1]["allowed_actions"] == [
        AgentAction.ANSWER,
        AgentAction.INSUFFICIENT,
    ]
    assert len(result["action_history"]) == 8
    assert result["next_action"] is AgentAction.INSUFFICIENT
