class AIError(Exception):
    """可安全写入 Article AI 错误字段的基础异常。"""


class LLMConfigurationError(AIError):
    """LLM 必要配置缺失。"""


class LLMTimeoutError(AIError):
    """LLM 请求超时。"""


class LLMConnectionError(AIError):
    """LLM 网络连接失败。"""


class LLMAuthenticationError(AIError):
    """LLM 鉴权失败。"""


class LLMRateLimitError(AIError):
    """LLM 服务触发限流。"""


class LLMServiceError(AIError):
    """LLM 服务端或其他 API 错误。"""


class LLMResponseError(AIError):
    """LLM 返回空内容或非法结构。"""
