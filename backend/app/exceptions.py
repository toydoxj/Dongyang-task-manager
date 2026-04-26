"""애플리케이션 예외 계층."""
from __future__ import annotations


class AppError(Exception):
    """모든 커스텀 예외의 부모."""

    error_code: str = "APP_ERROR"
    status_code: int = 500

    def __init__(self, message: str = "오류가 발생했습니다") -> None:
        self.message = message
        super().__init__(message)


class NotionApiError(AppError):
    """노션 API 호출 실패."""

    error_code = "NOTION_API_ERROR"
    status_code = 502


class ValidationError(AppError):
    """입력 검증 실패."""

    error_code = "VALIDATION_ERROR"
    status_code = 422


class NotFoundError(AppError):
    """리소스 미발견."""

    error_code = "NOT_FOUND"
    status_code = 404
