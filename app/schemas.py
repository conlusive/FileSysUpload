"""Pydantic-схеми запитів і відповідей API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Час життя токена, секунд")


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    content_type: str
    kind: Literal["image", "document"]
    size_bytes: int
    sha256: str
    width: int | None = None
    height: int | None = None
    optimized_size: int | None = None
    thumbnail_size: int | None = None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def download_url(self) -> str:
        return f"/files/{self.id}/download"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def thumbnail_url(self) -> str | None:
        return f"/files/{self.id}/download?variant=thumbnail" if self.thumbnail_size else None


class FileList(BaseModel):
    items: list[FileOut]
    total: int
    limit: int
    offset: int
