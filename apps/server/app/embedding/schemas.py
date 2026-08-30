from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenChunk:
    """按 token 切分后的正文片段。"""

    chunk_index: int
    content: str
    token_count: int


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """已取得向量、可供数据库原子替换的完整切片。"""

    chunk_index: int
    content: str
    token_count: int
    embedding: list[float]
    metadata: dict[str, object]
