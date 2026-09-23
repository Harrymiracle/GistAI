import logging

from app.crawler.browser_fetcher import PlaywrightFetcher
from app.crawler.errors import CrawlerError, CrawlerFallbackError, UnsafeUrlError
from app.crawler.extractor import ArticleExtractor, ExtractedArticle
from app.crawler.http_fetcher import HttpFetcher


logger = logging.getLogger(__name__)


class CrawlerService:
    """优先普通 HTTP，失败后使用 Playwright 获取渲染 HTML。"""

    def __init__(
        self,
        fetcher: HttpFetcher,
        extractor: ArticleExtractor,
        browser_fetcher: PlaywrightFetcher | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._extractor = extractor
        self._browser_fetcher = browser_fetcher

    def fetch_article(self, url: str) -> ExtractedArticle:
        try:
            fetched = self._fetcher.fetch(url)
            extracted = self._extractor.extract(fetched.html, fetched.final_url)
        except UnsafeUrlError:
            raise
        except CrawlerError as http_error:
            browser_fetcher = self._browser_fetcher
            if browser_fetcher is None:
                raise
            logger.info("普通 HTTP 阶段失败，开始 Playwright fallback：%s", http_error)
            return self._fetch_with_browser(url, http_error, browser_fetcher)

        logger.info("普通 HTTP 抓取和正文提取成功，无需启动 Playwright")
        return extracted

    def _fetch_with_browser(
        self,
        url: str,
        http_error: CrawlerError,
        browser_fetcher: PlaywrightFetcher,
    ) -> ExtractedArticle:
        try:
            fetched = browser_fetcher.fetch(url)
            return self._extractor.extract(fetched.html, fetched.final_url)
        except CrawlerError as browser_error:
            raise CrawlerFallbackError(
                f"普通 HTTP 阶段失败：{http_error}；"
                f"Playwright 阶段失败：{browser_error}"
            ) from browser_error
