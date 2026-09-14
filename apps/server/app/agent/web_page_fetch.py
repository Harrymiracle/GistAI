from typing import Protocol

from app.agent.schemas import WebPageContentResult
from app.crawler.errors import UnsafeUrlError
from app.crawler.service import CrawlerService


class WebPageValidationError(Exception):
    """网页地址未通过现有抓取链路的安全校验。"""


class WebPageFetchProvider(Protocol):
    """供 Agent 抓取已搜索网页正文的边界。"""

    def fetch(self, url: str) -> WebPageContentResult: ...


class WebPageFetchService:
    """将现有 CrawlerService 转换为 Agent 所需的网页全文结果。"""

    def __init__(self, crawler: CrawlerService) -> None:
        self._crawler = crawler

    def fetch(self, url: str) -> WebPageContentResult:
        try:
            extracted = self._crawler.fetch_article(url)
        except UnsafeUrlError as exc:
            raise WebPageValidationError("网页地址不可访问") from exc
        return WebPageContentResult(
            url=url,
            title=extracted.title,
            clean_content=extracted.clean_content,
            source=extracted.source_name,
            published_at=extracted.published_at,
        )
