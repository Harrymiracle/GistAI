from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


TagName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class TagCreate(BaseModel):
    """创建 Tag 请求。"""

    name: TagName


class TagUpdate(BaseModel):
    """修改 Tag 名称请求。"""

    name: TagName


class TagRead(BaseModel):
    """Tag 响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
