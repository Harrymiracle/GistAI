from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.config import settings


QuestionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]
AnswerText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
]
TagId = Annotated[int, Field(gt=0)]


class AskRequest(BaseModel):
    """单轮知识库问答请求。"""

    question: QuestionText
    top_k: int = Field(default=settings.rag_top_k, ge=1, le=50)
    favorite_only: bool = False
    tag_ids: list[TagId] = Field(default_factory=list, max_length=50)

    @field_validator("tag_ids", mode="after")
    @classmethod
    def deduplicate_tag_ids(cls, tag_ids: list[int]) -> list[int]:
        return list(dict.fromkeys(tag_ids))


class GroundedAnswerResult(BaseModel):
    """由 LLM 返回并经过校验的回答结构。"""

    model_config = ConfigDict(extra="forbid")

    answer: AnswerText


class RAGSource(BaseModel):
    article_id: int
    title: str | None
    chunk_id: int
    chunk_index: int
    excerpt: str
    score: float


class AskData(BaseModel):
    answer: str
    sources: list[RAGSource]
