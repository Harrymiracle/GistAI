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


class ManualContentInvalidError(AppError):
    """手动正文清洗后无效。"""

    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=422,
            code=42202,
            message=message,
        )
