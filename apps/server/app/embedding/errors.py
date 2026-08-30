class EmbeddingError(Exception):
    """可安全写入 Article Embedding 错误字段的基础异常。"""


class EmbeddingConfigurationError(EmbeddingError):
    """Embedding 必要配置缺失或无效。"""


class EmbeddingTimeoutError(EmbeddingError):
    """Embedding 请求超时。"""


class EmbeddingConnectionError(EmbeddingError):
    """Embedding 网络连接失败。"""


class EmbeddingAuthenticationError(EmbeddingError):
    """Embedding 鉴权失败。"""


class EmbeddingRateLimitError(EmbeddingError):
    """Embedding 服务触发限流。"""


class EmbeddingServiceError(EmbeddingError):
    """Embedding 服务端或其他 API 错误。"""


class EmbeddingResponseError(EmbeddingError):
    """Embedding 返回空内容、数量错误或非法向量。"""
