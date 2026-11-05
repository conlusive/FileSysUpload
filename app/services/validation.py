"""Перевірка завантажених файлів: визначення типу за вмістом і очищення імені."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import status

from app.errors import UploadRejected


@dataclass(frozen=True)
class FileType:
    """Дозволений тип файлу."""

    name: str
    mime: str
    extensions: tuple[str, ...]   # перше значення це канонічне розширення для збереження
    kind: str                     # "image" або "document"


JPEG = FileType("jpeg", "image/jpeg", (".jpg", ".jpeg"), "image")
PNG = FileType("png", "image/png", (".png",), "image")
GIF = FileType("gif", "image/gif", (".gif",), "image")
WEBP = FileType("webp", "image/webp", (".webp",), "image")
PDF = FileType("pdf", "application/pdf", (".pdf",), "document")

ALLOWED_TYPES: tuple[FileType, ...] = (JPEG, PNG, GIF, WEBP, PDF)
HEAD_SIZE = 32  # скільки перших байтів потрібно для визначення типу

_GENERIC_MIME = {"", "application/octet-stream"}


def sniff_type(head: bytes) -> FileType | None:
    """Визначає тип за «магічними» байтами початку файлу (сигнатурою)."""
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith((b"GIF87a", b"GIF89a")):
        return GIF
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    if head.startswith(b"%PDF-"):
        return PDF
    return None


def sanitize_filename(raw: str | None) -> str:
    """Залишає лише безпечне базове ім'я: без шляху, керуючих символів, довге ім'я обрізається до 255 символів."""
    name = (raw or "").replace("\x00", "")
    # Беремо останню компоненту як для POSIX, так і для Windows-шляхів.
    name = PureWindowsPath(PurePosixPath(name).name).name
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = name.strip(" .")
    if not name:
        return "file"
    if len(name) > 255:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 16:
            name = stem[: 255 - len(ext) - 1] + "." + ext
        else:
            name = name[:255]
    return name


def validate_declared(file_type: FileType, filename: str, content_type: str | None) -> None:
    """Звіряє розширення та заявлений Content-Type з реальним типом вмісту."""
    suffix = PurePosixPath(filename.lower()).suffix
    if suffix not in file_type.extensions:
        raise UploadRejected(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"File extension '{suffix or '(none)'}' does not match the detected content type {file_type.mime}.",
        )
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in _GENERIC_MIME and declared != file_type.mime:
        # image/jpg це поширена помилкова назва JPEG
        if not (file_type is JPEG and declared == "image/jpg"):
            raise UploadRejected(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"Declared Content-Type '{declared}' does not match the detected type {file_type.mime}.",
            )


_SAFE_RE = re.compile(r"^[0-9a-f]{32}$")


def is_valid_file_id(value: str) -> bool:
    return bool(_SAFE_RE.match(value))
