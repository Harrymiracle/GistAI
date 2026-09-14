from enum import StrEnum
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints


KnowledgeQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]
DecisionReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]
ResultIndex = Annotated[int, Field(ge=0, strict=True)]
WebResultText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=5000),
]
PublishedAt = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class KnowledgeSearchInput(BaseModel):
    """受程序约束的知识库检索输入。"""

    model_config = ConfigDict(extra="forbid")

    query: KnowledgeQuery
    top_k: int = Field(default=5, ge=1, le=10)


class KnowledgeSearchResult(BaseModel):
    """写入 AgentState 的最小知识库候选证据。"""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
    )

    article_id: int
    chunk_id: int
    title: str | None
    chunk_text: str = Field(validation_alias="excerpt")
    score: float


class WebSearchInput(BaseModel):
    """受程序约束的外部搜索输入。"""

    model_config = ConfigDict(extra="forbid")

    query: KnowledgeQuery
    max_results: int = Field(default=5, ge=1, le=10)


class WebSearchResult(BaseModel):
    """与具体搜索厂商无关的搜索级弱证据。"""

    model_config = ConfigDict(extra="forbid")

    title: WebResultText
    url: HttpUrl
    snippet: WebResultText
    source: WebResultText
    published_at: PublishedAt | None = None


class ArticleContentResult(BaseModel):
    """Agent 可见的最小知识库文章全文结果。"""

    model_config = ConfigDict(extra="forbid")

    article_id: int
    title: str | None
    clean_content: str
    url: str | None = None
    author: str | None = None
    published_at: datetime | None = None


class WebPageContentResult(BaseModel):
    """Agent 可见的最小外部网页全文结果。"""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None
    clean_content: str
    source: str | None = None
    published_at: datetime | None = None


class FullTextEvidence(BaseModel):
    """经临时切片、相关性选择和预算限制后的全文证据。"""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["knowledge_base_fulltext", "web_fulltext"]
    content: str
    token_count: int = Field(gt=0)
    temporary_chunk_indexes: list[int]
    article_id: int | None = None
    title: str | None = None
    url: str | None = None
    source: str | None = None
    published_at: datetime | None = None


class AgentAction(StrEnum):
    """后续 Agent 流程允许使用的动作类型。"""

    KNOWLEDGE_SEARCH = "knowledge_search"
    REWRITE_QUERY = "rewrite_query"
    WEB_SEARCH = "web_search"
    GET_ARTICLE_CONTENT = "get_article_content"
    FETCH_WEB_PAGE = "fetch_web_page"
    ANSWER = "answer"
    PARTIAL_ANSWER = "partial_answer"
    INSUFFICIENT = "insufficient"


class AgentIntent(StrEnum):
    """单轮问题对知识来源和时效性的意图。"""

    KNOWLEDGE_BASE_ONLY = "knowledge_base_only"
    FRESH_INFORMATION = "fresh_information"
    OPEN = "open"


class EvidenceStatus(StrEnum):
    """证据是否足以回答问题的基础状态。"""

    UNKNOWN = "unknown"
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class AgentDecision(BaseModel):
    """LLM 返回且由程序再次约束的证据决策。"""

    model_config = ConfigDict(extra="forbid")

    evidence_status: EvidenceStatus
    reason: DecisionReason
    next_action: AgentAction
    selected_result_indexes: list[ResultIndex] = Field(
        default_factory=list,
        max_length=10,
    )
    selected_web_result_indexes: list[ResultIndex] = Field(
        default_factory=list,
        max_length=10,
    )
    selected_article_result_index: ResultIndex | None = None
    selected_web_page_result_index: ResultIndex | None = None
    selected_article_content_indexes: list[ResultIndex] = Field(
        default_factory=list,
        max_length=10,
    )
    selected_web_page_content_indexes: list[ResultIndex] = Field(
        default_factory=list,
        max_length=10,
    )


class QueryRewriteResult(BaseModel):
    """LLM 返回的单一改写查询。"""

    model_config = ConfigDict(extra="forbid")

    query: KnowledgeQuery


class IntentClassification(BaseModel):
    """LLM 对模糊用户意图的结构化分类。"""

    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    reason: DecisionReason


class IntentDecision(BaseModel):
    """经过程序策略归一化的单轮联网权限。"""

    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    allow_web: bool
    requires_freshness: bool
    reason: DecisionReason
