from typing import Generic, TypeVar

from pydantic import BaseModel


DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    """统一 API 响应结构。"""

    code: int = 0
    message: str = "success"
    data: DataT
