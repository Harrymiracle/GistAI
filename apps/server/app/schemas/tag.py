from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


TagName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class TagCreate(BaseModel):
    """创建 Tag 请求。"""

    model_config = ConfigDict(extra="forbid")

    name: TagName


class TagUpdate(BaseModel):
    """修改 Tag 名称请求。"""

    model_config = ConfigDict(extra="forbid")

    name: TagName


class TagRead(BaseModel):
    """Tag 响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    article_count: int
    created_at: datetime
    updated_at: datetime


class PendingTopicSource(BaseModel):
    """待整理主题的来源文章。"""

    article_id: int
    title: str | None


class PendingTagRead(BaseModel):
    """待整理主题及其来源。"""

    id: int
    name: str
    created_at: datetime
    sources: list[PendingTopicSource]


class TagMergeRequest(BaseModel):
    """归入已有正式主题的请求。"""

    model_config = ConfigDict(extra="forbid")

    target_tag_id: int
