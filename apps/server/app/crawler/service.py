from app.crawler.extractor import ArticleExtractor, ExtractedArticle
from app.crawler.http_fetcher import HttpFetcher


class CrawlerService:
    """编排普通 HTTP 抓取、正文提取和清洗。"""

    def __init__(self, fetcher: HttpFetcher, extractor: ArticleExtractor) -> None:
        self._fetcher = fetcher
        self._extractor = extractor

    def fetch_article(self, url: str) -> ExtractedArticle:
        fetched = self._fetcher.fetch(url)
        return self._extractor.extract(fetched.html, fetched.final_url)
