"""Конфігурація застосунку. Значення читаються зі змінних середовища."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SECRET = "dev-only-secret-change-me-0123456789abcdef"


@dataclass(frozen=True)
class Settings:
    """Незмінний набір налаштувань; у тестах створюється напряму."""

    secret_key: str = DEFAULT_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./data/app.db"
    storage_dir: Path = Path("./data/storage")
    max_upload_bytes: int = 10 * 1024 * 1024      # 10 МіБ
    max_image_pixels: int = 40_000_000             # захист від «бомб розпакування»
    chunk_size: int = 1024 * 1024                  # розмір порції при читанні
    optimized_max_side: int = 1600                 # довша сторона «оптимізованої» копії
    thumbnail_max_side: int = 256                  # довша сторона мініатюри
    jpeg_quality: int = 85

    @classmethod
    def from_env(cls) -> "Settings":
        """Створює налаштування зі змінних середовища (з типовими значеннями)."""
        env = os.environ.get
        return cls(
            secret_key=env("SECRET_KEY", DEFAULT_SECRET),
            access_token_expire_minutes=int(env("ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
            database_url=env("DATABASE_URL", "sqlite:///./data/app.db"),
            storage_dir=Path(env("STORAGE_DIR", "./data/storage")),
            max_upload_bytes=int(env("MAX_UPLOAD_MB", "10")) * 1024 * 1024,
            max_image_pixels=int(env("MAX_IMAGE_PIXELS", "40000000")),
            optimized_max_side=int(env("OPTIMIZED_MAX_SIDE", "1600")),
            thumbnail_max_side=int(env("THUMBNAIL_MAX_SIDE", "256")),
            jpeg_quality=int(env("JPEG_QUALITY", "85")),
        )

    @property
    def uses_default_secret(self) -> bool:
        return self.secret_key == DEFAULT_SECRET
