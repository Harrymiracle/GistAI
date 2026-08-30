from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.core.config import settings


Keyword = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class KeywordSearchParams(BaseModel):
    """关键词搜索查询参数。"""

    q: Keyword
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class KeywordSearchItem(BaseModel):
    """不包含完整正文的关键词搜索结果。"""

    model_config = ConfigDict(from_attributes=True)

    article_id: int = Field(validation_alias="id")
    title: str | None
    one_sentence_summary: str | None
    source_type: str
    source_name: str | None
    published_at: datetime | None
    tags: list[str] = Field(default_factory=list)
    favorite: bool
    status: str
    created_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def serialize_tag_names(cls, tags: object) -> object:
        if isinstance(tags, list):
            return [getattr(tag, "name", tag) for tag in tags]
        return tags


class KeywordSearchData(BaseModel):
    """与 Article List 一致的分页结果结构。"""

    items: list[KeywordSearchItem]
    total: int
    page: int
    page_size: int


SemanticQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]


class SemanticSearchRequest(BaseModel):
    """语义搜索请求。"""

    query: SemanticQuery
    top_k: int = Field(default=settings.rag_top_k, ge=1, le=50)


class SemanticSearchItem(BaseModel):
    """每篇 Article 仅保留最高分 Chunk 的语义搜索结果。"""

    model_config = ConfigDict(from_attributes=True)

    article_id: int
    title: str | None
    chunk_id: int
    chunk_index: int
    excerpt: str
    score: float
    one_sentence_summary: str | None
    source_url: str
    source_name: str | None


class SemanticSearchData(BaseModel):
    items: list[SemanticSearchItem]
    top_k: int
    similarity_threshold: float
