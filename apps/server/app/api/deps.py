from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crawler.browser_fetcher import PlaywrightFetcher
from app.crawler.extractor import ArticleExtractor
from app.crawler.http_fetcher import HttpFetcher
from app.crawler.service import CrawlerService
from app.db.session import SessionLocal


DEFAULT_USER_ID = 1


def get_db() -> Generator[Session, None, None]:
    """为单次请求提供数据库会话。"""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user_id() -> int:
    """返回 V1 默认用户，后续可替换为认证结果。"""

    return DEFAULT_USER_ID


def get_crawler_service() -> CrawlerService:
    """按当前配置构建普通网页抓取服务。"""

    return CrawlerService(
        fetcher=HttpFetcher(
            timeout_seconds=settings.fetch_timeout_seconds,
            max_redirects=settings.fetch_max_redirects,
            user_agent=settings.fetch_user_agent,
        ),
        extractor=ArticleExtractor(
            min_content_chars=settings.fetch_min_content_chars,
        ),
        browser_fetcher=PlaywrightFetcher(
            navigation_timeout_seconds=settings.playwright_navigation_timeout_seconds,
            network_idle_timeout_seconds=settings.playwright_network_idle_timeout_seconds,
            user_agent=settings.fetch_user_agent,
        ),
    )


def get_min_content_chars() -> int:
    """返回网页提取和手动正文共用的最小正文长度。"""

    return settings.fetch_min_content_chars
