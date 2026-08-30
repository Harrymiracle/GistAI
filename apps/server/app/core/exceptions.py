from typing import Any


class AppError(Exception):
    """可安全返回给 API 调用方的业务异常。"""

    def __init__(
        self,
        *,
        status_code: int,
        code: int,
        message: str,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.data = data


class ArticleNotFoundError(AppError):
    """Article 不存在。"""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code=40401,
            message="Article 不存在",
        )


class ArticleAlreadyExistsError(AppError):
    """同一用户已保存相同 URL。"""

    def __init__(self, article_id: int) -> None:
        super().__init__(
            status_code=409,
            code=40901,
            message="Article 已存在",
            data={"article_id": article_id},
        )


class ArticleProcessingConflictError(AppError):
    """Article 当前已有同步处理操作。"""

    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code=40903,
            message="Article 正在处理中，请勿重复操作",
        )


class ArticleContentUnavailableError(AppError):
    """Article 没有可用于重新生成的有效正文。"""

    def __init__(self, message: str = "Article 没有有效正文") -> None:
        super().__init__(status_code=422, code=42203, message=message)


class ArticleSourceUrlInvalidError(AppError):
    """Article 没有可供重新抓取的 HTTP URL。"""

    def __init__(self) -> None:
        super().__init__(
            status_code=422,
            code=42204,
            message="Article 没有可重新抓取的有效 URL",
        )


class ManualContentInvalidError(AppError):
    """手动正文清洗后无效。"""

    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=422,
            code=42202,
            message=message,
        )


class TagNotFoundError(AppError):
    """Tag 不存在。"""

    def __init__(self) -> None:
        super().__init__(
            status_code=404,
            code=40402,
            message="Tag 不存在",
        )


class TagAlreadyExistsError(AppError):
    """同一用户已存在同名 Tag。"""

    def __init__(self, tag_id: int) -> None:
        super().__init__(
            status_code=409,
            code=40902,
            message="Tag 已存在",
            data={"tag_id": tag_id},
        )


class SemanticSearchEmbeddingError(AppError):
    """语义搜索生成查询向量失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=502,
            code=50201,
            message=message,
        )


class RAGLLMError(AppError):
    """RAG 生成回答时的安全 LLM 错误。"""

    def __init__(self, message: str) -> None:
        super().__init__(status_code=502, code=50202, message=message)
