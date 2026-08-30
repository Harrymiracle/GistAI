from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.common import ApiResponse
from app.schemas.tag import TagCreate, TagRead, TagUpdate
from app.services.tag import TagService


router = APIRouter(prefix="/tags", tags=["tags"])

DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]


@router.get("", response_model=ApiResponse[list[TagRead]])
def list_tags(
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[list[TagRead]]:
    tags = TagService.list_tags(session, user_id)
    return ApiResponse(
        code=20000,
        message="Tag 列表查询成功",
        data=[TagRead.model_validate(tag) for tag in tags],
    )


@router.post(
    "",
    response_model=ApiResponse[TagRead],
    status_code=status.HTTP_201_CREATED,
)
def create_tag(
    payload: TagCreate,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[TagRead]:
    tag = TagService.create_tag(session, user_id, payload.name)
    return ApiResponse(
        code=20100,
        message="Tag 创建成功",
        data=TagRead.model_validate(tag),
    )


@router.patch("/{tag_id}", response_model=ApiResponse[TagRead])
def update_tag(
    tag_id: int,
    payload: TagUpdate,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[TagRead]:
    tag = TagService.update_tag(session, tag_id, user_id, payload.name)
    return ApiResponse(
        code=20000,
        message="Tag 修改成功",
        data=TagRead.model_validate(tag),
    )


@router.delete("/{tag_id}", response_model=ApiResponse[dict[str, int]])
def delete_tag(
    tag_id: int,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[dict[str, int]]:
    deleted_id = TagService.delete_tag(session, tag_id, user_id)
    return ApiResponse(
        code=20000,
        message="Tag 删除成功",
        data={"tag_id": deleted_id},
    )
