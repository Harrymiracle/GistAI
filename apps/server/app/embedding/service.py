from typing import Protocol

from app.embedding.chunker import TokenChunker
from app.embedding.errors import EmbeddingResponseError
from app.embedding.schemas import EmbeddedChunk


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ArticleEmbeddingProcessor(Protocol):
    def generate(self, clean_content: str) -> list[EmbeddedChunk]: ...


class EmbeddingService:
    """先在内存中完成全部切片和向量，再交由 Article Service 持久化。"""

    def __init__(
        self,
        *,
        chunker: TokenChunker,
        client: EmbeddingClient,
        batch_size: int,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        self._chunker = chunker
        self._client = client
        self._batch_size = batch_size

    def generate(self, clean_content: str) -> list[EmbeddedChunk]:
        chunks = self._chunker.chunk(clean_content)
        if not chunks:
            raise EmbeddingResponseError("正文未生成有效切片")

        vectors: list[list[float]] = []
        for start in range(0, len(chunks), self._batch_size):
            batch = chunks[start : start + self._batch_size]
            batch_vectors = self._client.embed([chunk.content for chunk in batch])
            if len(batch_vectors) != len(batch):
                raise EmbeddingResponseError("Embedding 返回数量与输入不一致")
            vectors.extend(batch_vectors)

        return [
            EmbeddedChunk(
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
                embedding=vector,
                metadata={
                    "tokenizer": self._chunker.tokenizer_name,
                    "chunk_size": self._chunker.chunk_size,
                    "chunk_overlap": self._chunker.overlap,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
