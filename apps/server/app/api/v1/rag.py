from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db, get_rag_service
from app.rag.schemas import AskData, AskRequest
from app.rag.service import RAGService
from app.schemas.common import ApiResponse


router = APIRouter(tags=["rag"])

DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]
RAGDependency = Annotated[RAGService, Depends(get_rag_service)]


@router.post("/ask", response_model=ApiResponse[AskData])
def ask(
    payload: AskRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    rag_service: RAGDependency,
) -> ApiResponse[AskData]:
    data = rag_service.ask(
        session,
        user_id,
        payload.question,
        top_k=payload.top_k,
        favorite_only=payload.favorite_only,
        tag_ids=payload.tag_ids,
    )
    return ApiResponse(code=20000, message="知识库问答成功", data=data)
