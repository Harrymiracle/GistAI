import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.crawler.errors import (
    CrawlerError,
    FetchConnectionError,
    FetchHttpError,
    FetchTimeoutError,
    UnsafeUrlError,
)
from app.crawler.http_fetcher import FetchResult, UrlSafetyValidator


logger = logging.getLogger(__name__)
PlaywrightFactory = Callable[[], Any]


class PlaywrightFetcher:
    """使用无头 Chromium 获取渲染后 HTML，并拦截内部网络请求。"""

    def __init__(
        self,
        *,
        navigation_timeout_seconds: float,
        network_idle_timeout_seconds: float,
        user_agent: str,
        validator: UrlSafetyValidator | None = None,
        playwright_factory: PlaywrightFactory = sync_playwright,
    ) -> None:
        self._navigation_timeout_ms = navigation_timeout_seconds * 1000
        self._network_idle_timeout_ms = network_idle_timeout_seconds * 1000
        self._user_agent = user_agent
        self._validator = validator or UrlSafetyValidator()
        self._playwright_factory = playwright_factory

    def fetch(self, url: str) -> FetchResult:
        self._validator.validate(url)
        blocked_navigation_errors: list[str] = []
        validated_origins: set[tuple[str, str, int | None]] = set()
        browser = None
        context = None
        page = None

        try:
            with self._playwright_factory() as playwright:
                try:
                    browser = playwright.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=self._user_agent,
                        service_workers="block",
                    )
                    context.route(
                        "**/*",
                        lambda route: self._handle_route(
                            route,
                            validated_origins,
                            blocked_navigation_errors,
                        ),
                    )
                    context.route_web_socket(
                        "**/*",
                        lambda web_socket: web_socket.close(code=1008),
                    )
                    page = context.new_page()

                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self._navigation_timeout_ms,
                    )
                    try:
                        page.wait_for_load_state(
                            "networkidle",
                            timeout=self._network_idle_timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        logger.info(
                            "Playwright 页面在限定时间内未达到 networkidle，继续提取当前 DOM"
                        )

                    if blocked_navigation_errors:
                        raise UnsafeUrlError(blocked_navigation_errors[0])

                    final_url = page.url
                    self._validator.validate(final_url)
                    if response is not None and response.status >= 400:
                        raise FetchHttpError(
                            f"Playwright 访问目标网页返回 HTTP {response.status}"
                        )
                    return FetchResult(html=page.content(), final_url=final_url)
                finally:
                    self._close_resource(page, "page")
                    self._close_resource(context, "context")
                    self._close_resource(browser, "browser")
        except CrawlerError:
            raise
        except PlaywrightTimeoutError as exc:
            if blocked_navigation_errors:
                raise UnsafeUrlError(blocked_navigation_errors[0]) from exc
            raise FetchTimeoutError("Playwright 加载网页超时") from exc
        except PlaywrightError as exc:
            if blocked_navigation_errors:
                raise UnsafeUrlError(blocked_navigation_errors[0]) from exc
            raise FetchConnectionError("Playwright 无法加载目标网页") from exc

    def _handle_route(
        self,
        route: Any,
        validated_origins: set[tuple[str, str, int | None]],
        blocked_navigation_errors: list[str],
    ) -> None:
        request = route.request
        request_url = request.url
        try:
            origin = self._origin_key(request_url)
            if origin not in validated_origins:
                self._validator.validate(request_url)
                validated_origins.add(origin)
        except CrawlerError as exc:
            if request.is_navigation_request():
                blocked_navigation_errors.append(str(exc))
            route.abort("blockedbyclient")
            return
        except ValueError:
            if request.is_navigation_request():
                blocked_navigation_errors.append("浏览器导航目标 URL 无效")
            route.abort("blockedbyclient")
            return
        route.continue_()

    @staticmethod
    def _origin_key(url: str) -> tuple[str, str, int | None]:
        parsed = urlsplit(url)
        return parsed.scheme, parsed.hostname or "", parsed.port

    @staticmethod
    def _close_resource(resource: Any, resource_name: str) -> None:
        if resource is None:
            return
        try:
            resource.close()
        except PlaywrightError:
            logger.warning("关闭 Playwright %s 失败", resource_name)
