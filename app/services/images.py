"""Обробка зображень: перевірка, виправлення орієнтації, зменшення, стиснення, мініатюри."""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from fastapi import status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.errors import UploadRejected

_ALPHA_MODES = {"RGBA", "LA", "PA"}


@dataclass(frozen=True)
class ImageResult:
    width: int
    height: int
    optimized_name: str
    optimized_size: int
    thumbnail_name: str
    thumbnail_size: int
    variant_mime: str


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in _ALPHA_MODES or (image.mode == "P" and "transparency" in image.info)


def _save(image: Image.Image, directory: Path, base_name: str, fmt: str, quality: int) -> Path:
    """Зберігає зображення як ``<base_name>.png`` або ``<base_name>.jpg`` (розширення додається явно)."""
    if fmt == "PNG":
        target = directory / f"{base_name}.png"
        image.save(target, format="PNG", optimize=True)
    else:
        target = directory / f"{base_name}.jpg"
        image.save(target, format="JPEG", quality=quality, optimize=True, progressive=True)
    return target


def _fit(image: Image.Image, max_side: int) -> Image.Image:
    """Повертає копію, зменшену так, щоб довша сторона не перевищувала max_side (без збільшення)."""
    copy = image.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return copy


def process_image(source: Path, out_dir: Path, file_id: str, settings: Settings) -> ImageResult:
    """Створює оптимізовану копію та мініатюру. Метадані (EXIF) не переносяться.

    Кидає ``UploadRejected`` (422), якщо файл пошкоджений або занадто великий за кількістю пікселів.
    """
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as opened:
                width, height = opened.size
                if width * height > settings.max_image_pixels:
                    raise UploadRejected(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        f"Image is too large: {width}x{height} pixels exceeds the limit.",
                    )
                opened.load()                                  # повне декодування: виявляє пошкодження
                image = ImageOps.exif_transpose(opened)        # враховуємо EXIF-орієнтацію
    except UploadRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise UploadRejected(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Image is corrupted or cannot be decoded."
        ) from exc

    width, height = image.size
    if _has_alpha(image):
        fmt, mime = "PNG", "image/png"
        image = image.convert("RGBA")
    else:
        fmt, mime = "JPEG", "image/jpeg"
        image = image.convert("RGB")

    optimized = _fit(image, settings.optimized_max_side)
    thumbnail = _fit(image, settings.thumbnail_max_side)
    opt_path = _save(optimized, out_dir, f"{file_id}_opt", fmt, settings.jpeg_quality)
    thumb_path = _save(thumbnail, out_dir, f"{file_id}_thumb", fmt, settings.jpeg_quality)
    return ImageResult(
        width=width,
        height=height,
        optimized_name=opt_path.name,
        optimized_size=opt_path.stat().st_size,
        thumbnail_name=thumb_path.name,
        thumbnail_size=thumb_path.stat().st_size,
        variant_mime=mime,
    )
