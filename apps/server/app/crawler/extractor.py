import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

import trafilatura
from trafilatura.metadata import extract_metadata

from app.crawler.cleaner import clean_text
from app.crawler.errors import ExtractionError


NON_WHITESPACE = re.compile(r"\s")


@dataclass(frozen=True)
class ExtractedArticle:
    """正文以及能够可靠提取到的网页元数据。"""

    clean_content: str
    title: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    source_name: str | None = None


class ArticleExtractor:
    """使用 trafilatura 提取正文，再执行项目级文本清洗。"""

    def __init__(self, min_content_chars: int) -> None:
        self._min_content_chars = min_content_chars

    def extract(self, html_content: str, url: str) -> ExtractedArticle:
        try:
            extracted = trafilatura.extract(
                html_content,
                url=url,
                include_comments=False,
                include_tables=True,
                favor_precision=True,
                output_format="txt",
            )
        except Exception as exc:
            raise ExtractionError("网页正文提取失败") from exc
        if not extracted:
            raise ExtractionError("未能从网页中提取正文")

        clean_content = clean_text(extracted)
        effective_length = len(NON_WHITESPACE.sub("", clean_content))
        if effective_length < self._min_content_chars:
            raise ExtractionError(
                f"提取正文过短，至少需要 {self._min_content_chars} 个非空白字符"
            )

        title, author, published_at, source_name = self._extract_metadata(
            html_content,
            url,
        )
        return ExtractedArticle(
            clean_content=clean_content,
            title=title,
            author=author,
            published_at=published_at,
            source_name=source_name,
        )

    @staticmethod
    def _extract_metadata(
        html_content: str,
        url: str,
    ) -> tuple[str | None, str | None, datetime | None, str | None]:
        try:
            metadata = extract_metadata(html_content, default_url=url)
        except Exception:
            metadata = None

        hostname = urlsplit(url).hostname
        if metadata is None:
            return None, None, None, hostname

        return (
            clean_text(metadata.title) if metadata.title else None,
            clean_text(metadata.author) if metadata.author else None,
            ArticleExtractor._parse_published_at(metadata.date),
            clean_text(metadata.sitename) if metadata.sitename else metadata.hostname or hostname,
        )

    @staticmethod
    def _parse_published_at(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
