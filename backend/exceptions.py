# backend/exceptions.py

from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppHTTPException(HTTPException):
    """
    带业务错误码的 HTTP 异常。
    前端拦截器根据 error_code 查找 i18n 翻译，替代硬编码英文 detail 直接展示。
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        detail: Optional[str] = None,
    ):
        super().__init__(status_code=status_code, detail=detail or error_code)
        self.error_code = error_code


async def app_http_exception_handler(request: Request, exc: AppHTTPException) -> JSONResponse:
    """
    AppHTTPException 的全局异常处理器。
    将 error_code 注入响应体，供前端 i18n 映射使用。
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": exc.error_code,
        },
    )
