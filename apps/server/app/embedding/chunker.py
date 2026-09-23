import tiktoken

from app.embedding.schemas import TokenChunk


class TokenChunker:
    """使用本地 BPE tokenizer 按 token 数切分正文。"""

    tokenizer_name = "cl100k_base"

    def __init__(self, *, chunk_size: int, overlap: int) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap 必须大于等于 0 且小于 chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._encoding = tiktoken.get_encoding(self.tokenizer_name)

    def chunk(self, content: str) -> list[TokenChunk]:
        """在 Unicode 字符边界上生成不超过 chunk_size 的 token 切片。"""

        if not content or not content.strip():
            return []

        chunks: list[TokenChunk] = []
        start = 0
        text_length = len(content)
        while start < text_length:
            end = self._largest_fitting_end(content, start)
            if end <= start:
                raise ValueError("正文包含无法切分的内容")

            chunk_content = content[start:end]
            token_count = self.count_tokens(chunk_content)
            if chunk_content.strip() and token_count > 0:
                chunks.append(
                    TokenChunk(
                        chunk_index=len(chunks),
                        content=chunk_content,
                        token_count=token_count,
                    )
                )

            if end >= text_length:
                break
            next_start = self._overlap_start(content, start, end)
            start = next_start if next_start > start else end

        return chunks

    def count_tokens(self, content: str) -> int:
        return len(self._encoding.encode(content))

    def _largest_fitting_end(self, content: str, start: int) -> int:
        low = start + 1
        high = len(content)
        best = start
        while low <= high:
            middle = (low + high) // 2
            token_count = self.count_tokens(content[start:middle])
            if token_count <= self.chunk_size:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        return best

    def _overlap_start(self, content: str, chunk_start: int, chunk_end: int) -> int:
        if self.overlap == 0:
            return chunk_end

        low = chunk_start + 1
        high = chunk_end
        best = chunk_end
        while low <= high:
            middle = (low + high) // 2
            token_count = self.count_tokens(content[middle:chunk_end])
            if token_count <= self.overlap:
                best = middle
                high = middle - 1
            else:
                low = middle + 1

        while best < chunk_end and self.count_tokens(content[best:chunk_end]) > self.overlap:
            best += 1
        return best
