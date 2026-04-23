from pydantic import BaseModel
from typing import Any, Generic, TypeVar

T = TypeVar("T")

class ResponseBase(BaseModel):
    """响应基础模型"""
    code: int = 200
    data: Any = None
    message: str | None = None

class SuccessResponse(ResponseBase):
    """成功响应"""
    code: int = 200

class ErrorResponse(ResponseBase):
    """错误响应"""
    code: int = 400

class ExceptionResponse(ResponseBase):
    """异常响应"""
    code: int = 401

class PaginationParams(BaseModel):
    """分页参数"""
    page: int = 1
    page_size: int = 10

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return min(self.page_size, 50)  # 最大50

class PaginatedResponse(BaseModel):
    """分页响应"""
    total: int
    page: int
    page_size: int
    items: list[Any]
