"""Приймання файлу: потокове читання, перевірка, обробка та збереження на диск і в БД."""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path

from fastapi import UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import UploadRejected, too_large
from app.models import StoredFile, User
from app.services.images import process_image
from app.services.validation import (
    HEAD_SIZE,
    sanitize_filename,
    sniff_type,
    validate_declared,
)

logger = logging.getLogger("app.storage")


class FileStorage:
    """Файлове сховище: ``<root>/<owner_id>/<файли>`` та ``<root>/.tmp`` для тимчасових файлів."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.tmp_dir = self.root / ".tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def owner_dir(self, owner_id: int) -> Path:
        path = self.root / str(owner_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path_of(self, owner_id: int, name: str) -> Path:
        """Повертає шлях до файлу, гарантуючи, що він лишається всередині сховища."""
        path = (self.root / str(owner_id) / name).resolve()
        if self.root not in path.parents:
            raise ValueError("path escapes storage root")
        return path

    def remove(self, *paths: Path) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - залежить від ОС
                logger.warning("Could not remove %s", path)


def _stream_to_temp(upload: UploadFile, storage: FileStorage, settings: Settings) -> tuple[Path, int, str, bytes]:
    """Читає завантаження порціями у тимчасовий файл, рахуючи розмір і SHA-256.

    Перевищення ліміту виявляється одразу під час читання, не вичерпуючи пам'ять.
    """
    tmp_path = storage.tmp_dir / f"{uuid.uuid4().hex}.part"
    sha = hashlib.sha256()
    total = 0
    head = b""
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = upload.file.read(settings.chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise too_large(settings.max_upload_bytes)
                if len(head) < HEAD_SIZE:
                    head += chunk[: HEAD_SIZE - len(head)]
                sha.update(chunk)
                out.write(chunk)
    except BaseException:
        storage.remove(tmp_path)
        raise
    return tmp_path, total, sha.hexdigest(), head


def ingest_upload(upload: UploadFile, owner: User, db: Session, storage: FileStorage, settings: Settings) -> StoredFile:
    """Повний цикл прийому файлу. Повертає збережений запис ``StoredFile``.

    Порядок: потокове читання -> визначення типу за сигнатурою -> звірка розширення/Content-Type ->
    обробка зображення -> атомарне переміщення на місце -> запис у БД. У разі помилки диск очищується.
    """
    original_name = sanitize_filename(upload.filename)
    tmp_path, size, digest, head = _stream_to_temp(upload, storage, settings)
    created: list[Path] = []
    try:
        if size == 0:
            raise UploadRejected(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty.")

        file_type = sniff_type(head)
        if file_type is None:
            raise UploadRejected(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "Unsupported or unrecognized file type. Allowed: JPEG, PNG, GIF, WebP, PDF.",
            )
        validate_declared(file_type, original_name, upload.content_type)

        file_id = uuid.uuid4().hex
        out_dir = storage.owner_dir(owner.id)
        stored_name = f"{file_id}{file_type.extensions[0]}"
        record = StoredFile(
            id=file_id,
            owner_id=owner.id,
            original_name=original_name,
            content_type=file_type.mime,
            kind=file_type.kind,
            size_bytes=size,
            sha256=digest,
            stored_name=stored_name,
        )

        if file_type.kind == "image":
            result = process_image(tmp_path, out_dir, file_id, settings)
            created += [out_dir / result.optimized_name, out_dir / result.thumbnail_name]
            record.width, record.height = result.width, result.height
            record.optimized_name, record.optimized_size = result.optimized_name, result.optimized_size
            record.thumbnail_name, record.thumbnail_size = result.thumbnail_name, result.thumbnail_size
            record.variant_mime = result.variant_mime

        final_path = out_dir / stored_name
        os.replace(tmp_path, final_path)      # атомарно в межах однієї файлової системи
        created.append(final_path)

        db.add(record)
        db.commit()
        logger.info("Stored file %s (%s, %d bytes) for user %s", file_id, file_type.mime, size, owner.id)
        return record
    except BaseException:
        db.rollback()
        storage.remove(tmp_path, *created)
        raise
