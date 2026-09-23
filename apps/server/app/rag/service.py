from typing import Protocol

from sqlalchemy.orm import Session

from app.ai.errors import AIError
from app.core.exceptions import RAGLLMError
from app.rag.schemas import AskData, RAGSource
from app.services.search import QueryEmbeddingService, SearchService, SemanticSearchHit


INSUFFICIENT_EVIDENCE_ANSWER = (
    "当前知识库中没有找到足够相关的内容，暂时无法基于已保存资料回答这个问题。"
)


class GroundedAnswerGenerator(Protocol):
    def generate_grounded_answer(self, question: str, context: str) -> str: ...


class RAGService:
    """编排语义召回、受限 Context 和 grounded LLM 回答。"""

    def __init__(
        self,
        *,
        embedding_service: QueryEmbeddingService,
        ai_service: GroundedAnswerGenerator,
        similarity_threshold: float,
        max_context_chars: int,
    ) -> None:
        self._embedding_service = embedding_service
        self._ai_service = ai_service
        self._similarity_threshold = similarity_threshold
        self._max_context_chars = max_context_chars

    def ask(
        self,
        session: Session,
        user_id: int,
        question: str,
        *,
        top_k: int,
        favorite_only: bool = False,
        tag_ids: list[int] | None = None,
    ) -> AskData:
        hits = SearchService.semantic_search(
            session,
            user_id,
            question,
            top_k=top_k,
            similarity_threshold=self._similarity_threshold,
            embedding_service=self._embedding_service,
            favorite_only=favorite_only,
            tag_ids=tag_ids,
        )
        if not hits:
            return AskData(answer=INSUFFICIENT_EVIDENCE_ANSWER, sources=[])

        context, sources = self._build_context(hits)
        if not sources:
            return AskData(answer=INSUFFICIENT_EVIDENCE_ANSWER, sources=[])

        try:
            answer = self._ai_service.generate_grounded_answer(question, context)
        except AIError as exc:
            raise RAGLLMError(str(exc)) from exc
        return AskData(answer=answer, sources=sources)

    def _build_context(
        self,
        hits: list[SemanticSearchHit],
    ) -> tuple[str, list[RAGSource]]:
        sections: list[str] = []
        sources: list[RAGSource] = []
        used_chars = 0

        for hit in hits:
            source_number = len(sources) + 1
            header = (
                f"[Source {source_number}]\n"
                f"Article ID: {hit.article_id}\n"
                f"Article: {hit.title or '未命名文章'}\n"
                f"Chunk ID: {hit.chunk_id}\n"
                f"Chunk Index: {hit.chunk_index}\n"
                "Content:\n"
            )
            separator_length = 2 if sections else 0
            available = self._max_context_chars - used_chars - separator_length - len(header)
            if available <= 0:
                break
            excerpt = hit.excerpt[:available]
            if not excerpt:
                continue
            section = f"{header}{excerpt}"
            sections.append(section)
            used_chars += separator_length + len(section)
            sources.append(
                RAGSource(
                    article_id=hit.article_id,
                    title=hit.title,
                    chunk_id=hit.chunk_id,
                    chunk_index=hit.chunk_index,
                    excerpt=excerpt,
                    score=hit.score,
                )
            )

        return "\n\n".join(sections), sources
