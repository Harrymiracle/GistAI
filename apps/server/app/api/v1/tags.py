from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.models.tag import Tag
from app.schemas.common import ApiResponse
from app.schemas.tag import PendingTagRead, PendingTopicSource, TagCreate, TagMergeRequest, TagRead, TagUpdate
from app.services.tag import TagService


router = APIRouter(prefix="/tags", tags=["tags"])

DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]


def _tag_read(tag: Tag, article_count: int) -> TagRead:
    return TagRead(
        id=tag.id,
        name=tag.name,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
        article_count=article_count,
    )


@router.get("", response_model=ApiResponse[list[TagRead]])
def list_tags(
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[list[TagRead]]:
    tags = TagService.list_tags(session, user_id)
    return ApiResponse(
        code=20000,
        message="Tag 列表查询成功",
        data=[_tag_read(tag, count) for tag, count in tags],
    )


@router.get("/pending", response_model=ApiResponse[list[PendingTagRead]])
def list_pending(
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[list[PendingTagRead]]:
    pending = TagService.list_pending(session, user_id)
    return ApiResponse(
        code=20000,
        message="待整理主题列表查询成功",
        data=[
            PendingTagRead(
                id=tag.id,
                name=tag.name,
                created_at=tag.created_at,
                sources=[PendingTopicSource(article_id=article_id, title=title) for article_id, title in sources],
            )
            for tag, sources in pending
        ],
    )


@router.post("/{tag_id}/promote", response_model=ApiResponse[TagRead])
def promote_pending(
    tag_id: int,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[TagRead]:
    tag = TagService.promote_pending(session, tag_id, user_id)
    return ApiResponse(
        code=20000,
        message="待整理主题已设为正式主题",
        data=_tag_read(tag, TagService.count_articles(session, tag.id, user_id)),
    )


@router.post("/{tag_id}/merge", response_model=ApiResponse[dict[str, int]])
def merge_pending(
    tag_id: int,
    payload: TagMergeRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[dict[str, int]]:
    result = TagService.merge_pending(session, tag_id, payload.target_tag_id, user_id)
    return ApiResponse(code=20000, message="待整理主题已归入正式主题", data=result)


@router.post("/{tag_id}/ignore", response_model=ApiResponse[dict[str, int]])
def ignore_pending(
    tag_id: int,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[dict[str, int]]:
    result = TagService.ignore_pending(session, tag_id, user_id)
    return ApiResponse(code=20000, message="待整理主题已忽略", data=result)


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
        data=_tag_read(tag, 0),
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
        data=_tag_read(tag, TagService.count_articles(session, tag.id, user_id)),
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
