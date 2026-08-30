from app.embedding.chunker import TokenChunker
from app.embedding.service import EmbeddingService


def test_token_chunker_uses_400_tokens_with_80_token_overlap() -> None:
    chunker = TokenChunker(chunk_size=400, overlap=80)
    content = "x " * 1000

    chunks = chunker.chunk(content)

    assert len(chunks) == 3
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].token_count == 400
    assert chunks[1].token_count == 400
    assert all(0 < chunk.token_count <= 400 for chunk in chunks)
    overlap_text = chunks[0].content[-160:]
    assert chunker.count_tokens(overlap_text) == 80
    assert chunks[1].content.startswith(overlap_text)


def test_token_chunker_preserves_short_unicode_article_as_one_chunk() -> None:
    chunker = TokenChunker(chunk_size=400, overlap=80)
    content = "这是一篇包含中文和 English 的短文章。"

    chunks = chunker.chunk(content)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == content
    assert chunks[0].token_count == chunker.count_tokens(content)


def test_token_chunker_returns_no_empty_chunks() -> None:
    chunker = TokenChunker(chunk_size=10, overlap=2)

    assert chunker.chunk("") == []
    assert chunker.chunk("   \n\t") == []
    assert all(chunk.content.strip() for chunk in chunker.chunk("正文内容 " * 30))


def test_embedding_service_batches_chunks_without_changing_order() -> None:
    chunker = TokenChunker(chunk_size=10, overlap=2)

    class RecordingClient:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls.append(texts)
            start = sum(len(call) for call in self.calls[:-1])
            return [[float(start + index)] * 1024 for index in range(len(texts))]

    client = RecordingClient()
    service = EmbeddingService(chunker=chunker, client=client, batch_size=2)

    result = service.generate("x " * 50)

    assert len(result) > 2
    assert all(len(call) <= 2 for call in client.calls)
    assert [text for call in client.calls for text in call] == [
        chunk.content for chunk in result
    ]
    assert [chunk.embedding[0] for chunk in result] == [
        float(index) for index in range(len(result))
    ]


def test_chunker_rejects_invalid_overlap() -> None:
    try:
        TokenChunker(chunk_size=400, overlap=400)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("overlap 等于 chunk_size 时应拒绝")
