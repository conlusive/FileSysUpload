"""Спільні винятки застосунку."""
from __future__ import annotations

from fastapi import HTTPException, status


class UploadRejected(HTTPException):
    """Файл відхилено під час перевірки; несе відповідний HTTP-статус."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


def too_large(limit_bytes: int) -> UploadRejected:
    return UploadRejected(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"File is too large. Maximum allowed size is {limit_bytes} bytes.",
    )
