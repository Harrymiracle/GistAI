class CrawlerError(Exception):
    """可安全写入 Article 抓取错误字段的异常。"""


class UnsafeUrlError(CrawlerError):
    """URL 指向不允许访问的内部网络资源。"""


class FetchTimeoutError(CrawlerError):
    """网页请求超时。"""


class FetchConnectionError(CrawlerError):
    """网页连接失败。"""


class FetchHttpError(CrawlerError):
    """网页返回不可接受的 HTTP 状态。"""


class ExtractionError(CrawlerError):
    """网页没有提取出有效正文。"""


class CrawlerFallbackError(CrawlerError):
    """普通 HTTP 与 Playwright 两个阶段均失败。"""
