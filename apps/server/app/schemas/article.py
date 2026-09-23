from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)


SourceType = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
]
OptionalName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
OptionalTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class ArticleCreate(BaseModel):
    """创建 Article 的请求参数。"""

    source_url: HttpUrl
    source_type: SourceType
    source_name: OptionalName | None = None
    title: OptionalTitle | None = None
    author: OptionalName | None = None
    published_at: datetime | None = None
    favorite: bool = False


class ArticleUpdate(BaseModel):
    """允许用户修改的 Article 字段。"""

    title: OptionalTitle | None = None
    source_name: OptionalName | None = None
    author: OptionalName | None = None
    published_at: datetime | None = None
    favorite: bool = False

    @model_validator(mode="after")
    def ensure_update_fields(self) -> "ArticleUpdate":
        if not self.model_fields_set:
            raise ValueError("至少提供一个可修改字段")
        return self


class ManualContentRequest(BaseModel):
    """用户提交手动正文的请求参数。"""

    content: str = Field(min_length=1)


class ArticleListItem(BaseModel):
    """文章列表中的轻量数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    source_url: str
    source_type: str
    source_name: str | None
    one_sentence_summary: str | None
    favorite: bool
    status: str
    fetch_status: str
    ai_status: str
    embedding_status: str
    created_at: datetime
    updated_at: datetime


class ArticleListData(BaseModel):
    """分页文章列表。"""

    items: list[ArticleListItem]
    total: int
    page: int
    page_size: int


class ArticleDetail(BaseModel):
    """Article 完整详情。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    source_type: str
    source_url: str
    source_name: str | None
    title: str | None
    author: str | None
    published_at: datetime | None
    clean_content: str | None
    content_hash: str | None
    one_sentence_summary: str | None
    detailed_summary: str | None
    key_points: list[str] | None
    tags: list[str] = Field(default_factory=list)
    favorite: bool
    status: str
    fetch_status: str
    ai_status: str
    embedding_status: str
    fetch_error: str | None
    ai_error: str | None
    embedding_error: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def serialize_tag_names(cls, tags: object) -> object:
        if isinstance(tags, list):
            return [getattr(tag, "name", tag) for tag in tags]
        return tags


class ArticleStatus(BaseModel):
    """Article 处理状态。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    fetch_status: str
    ai_status: str
    embedding_status: str
    fetch_error: str | None
    ai_error: str | None
    embedding_error: str | None


class ArticleDeleteResult(BaseModel):
    """删除 Article 的结果。"""

    article_id: int


class ArticleReprocessData(BaseModel):
    """完整重处理结果，并明确正文是否未变化。"""

    content_unchanged: bool
    article: ArticleDetail
