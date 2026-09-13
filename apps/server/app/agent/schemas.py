from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


KnowledgeQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
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


class EvidenceStatus(StrEnum):
    """证据是否足以回答问题的基础状态。"""

    UNKNOWN = "unknown"
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
