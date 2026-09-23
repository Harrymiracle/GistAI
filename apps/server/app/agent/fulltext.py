import re
from collections import defaultdict
from typing import Any

from app.agent.schemas import FullTextEvidence
from app.embedding.chunker import TokenChunker


class FullTextEvidenceSelector:
    """从单轮全文结果中选择相关临时切片，并应用共享 token 预算。"""

    def __init__(
        self,
        *,
        chunker: TokenChunker,
        max_context_tokens: int,
    ) -> None:
        if max_context_tokens <= 0:
            raise ValueError("max_context_tokens 必须大于 0")
        self._chunker = chunker
        self.max_context_tokens = max_context_tokens

    def select(
        self,
        *,
        query: str,
        article_contents: list[dict[str, Any]],
        web_page_contents: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        terms = _query_terms(query)
        candidates: list[dict[str, Any]] = []
        order = 0
        for source_index, item in enumerate(article_contents):
            order = self._append_candidates(
                candidates,
                item=item,
                source_type="knowledge_base_fulltext",
                source_index=source_index,
                terms=terms,
                order=order,
            )
        for source_index, item in enumerate(web_page_contents):
            order = self._append_candidates(
                candidates,
                item=item,
                source_type="web_fulltext",
                source_index=source_index,
                terms=terms,
                order=order,
            )

        candidates.sort(key=lambda item: (-item["score"], item["order"]))
        selected: list[dict[str, Any]] = []
        remaining = self.max_context_tokens
        for candidate in candidates:
            token_count = candidate["token_count"]
            if token_count > remaining:
                continue
            selected.append(candidate)
            remaining -= token_count
            if remaining == 0:
                break

        grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for item in selected:
            grouped[(item["source_type"], item["source_index"])].append(item)

        article_evidence: list[dict[str, Any]] = []
        web_evidence: list[dict[str, Any]] = []
        for (source_type, source_index), chunks in grouped.items():
            source_item = (
                article_contents[source_index]
                if source_type == "knowledge_base_fulltext"
                else web_page_contents[source_index]
            )
            evidence = FullTextEvidence(
                source_type=source_type,
                content="\n\n".join(chunk["content"] for chunk in chunks),
                token_count=sum(chunk["token_count"] for chunk in chunks),
                temporary_chunk_indexes=[chunk["chunk_index"] for chunk in chunks],
                article_id=source_item.get("article_id"),
                title=source_item.get("title"),
                url=source_item.get("url"),
                source=source_item.get("source"),
                published_at=source_item.get("published_at"),
            ).model_dump(mode="json")
            if source_type == "knowledge_base_fulltext":
                article_evidence.append(evidence)
            else:
                web_evidence.append(evidence)
        return article_evidence, web_evidence

    def _append_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        item: dict[str, Any],
        source_type: str,
        source_index: int,
        terms: set[str],
        order: int,
    ) -> int:
        for chunk in self._chunker.chunk(str(item["clean_content"])):
            lowered = chunk.content.lower()
            score = sum(lowered.count(term) for term in terms)
            candidates.append(
                {
                    "source_type": source_type,
                    "source_index": source_index,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "token_count": chunk.token_count,
                    "score": score,
                    "order": order,
                }
            )
            order += 1
        return order


def _query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", query.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) == 1:
                terms.add(token)
            else:
                terms.update(token[index : index + 2] for index in range(len(token) - 1))
        else:
            terms.add(token)
    return terms
