"""Ендпоінти керування файлами: завантаження, список, метадані, скачування, видалення."""
from __future__ import annotations

from pathlib import PurePath
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.deps import get_current_user, get_db, get_settings, get_storage
from app.models import StoredFile, User
from app.schemas import FileList, FileOut
from app.services.storage import FileStorage, ingest_upload

router = APIRouter(prefix="/files", tags=["files"])

FileId = Path(pattern=r"^[0-9a-f]{32}$", description="Ідентифікатор файлу (32 hex-символи)")
Variant = Literal["original", "optimized", "thumbnail"]


def _get_owned(db: Session, user: User, file_id: str) -> StoredFile:
    """Повертає файл власника; чужі й неіснуючі файли однаково дають 404 (не розкриваємо існування)."""
    record = db.get(StoredFile, file_id)
    if record is None or record.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return record


@router.post("", response_model=FileOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(..., description="Файл для завантаження (multipart/form-data)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> StoredFile:
    """Завантажує файл, перевіряє його, обробляє зображення та зберігає метадані."""
    return ingest_upload(file, user, db, storage, settings)


@router.get("", response_model=FileList)
def list_files(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kind: Literal["image", "document"] | None = None,
    q: str | None = Query(None, min_length=1, max_length=100, description="Пошук за частиною імені"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileList:
    """Список власних файлів (нові першими) з пагінацією та фільтрами."""
    conditions = [StoredFile.owner_id == user.id]
    if kind:
        conditions.append(StoredFile.kind == kind)
    if q:
        conditions.append(StoredFile.original_name.icontains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(StoredFile).where(*conditions)) or 0
    rows = db.scalars(
        select(StoredFile)
        .where(*conditions)
        .order_by(StoredFile.created_at.desc(), StoredFile.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return FileList(items=[FileOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{file_id}", response_model=FileOut)
def get_file_info(file_id: str = FileId, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StoredFile:
    """Метадані одного файлу."""
    return _get_owned(db, user, file_id)


@router.get("/{file_id}/download")
def download_file(
    file_id: str = FileId,
    variant: Variant = "original",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> FileResponse:
    """Віддає файл (оригінал, оптимізовану копію або мініатюру) як вкладення."""
    record = _get_owned(db, user, file_id)
    if variant == "original":
        name, media_type, download_name = record.stored_name, record.content_type, record.original_name
    else:
        name = record.optimized_name if variant == "optimized" else record.thumbnail_name
        if not name:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Variant '{variant}' is not available for this file.")
        media_type = record.variant_mime or "application/octet-stream"
        download_name = f"{PurePath(record.original_name).stem}_{variant}{PurePath(name).suffix}"
    path = storage.path_of(record.owner_id, name)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File content is missing on the server.")
    return FileResponse(path, media_type=media_type, filename=download_name,
                        headers={"Cache-Control": "private, max-age=0"})


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: str = FileId,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> Response:
    """Видаляє запис у БД і всі пов'язані файли на диску."""
    record = _get_owned(db, user, file_id)
    names = [n for n in (record.stored_name, record.optimized_name, record.thumbnail_name) if n]
    paths = [storage.path_of(record.owner_id, n) for n in names]
    db.delete(record)
    db.commit()
    storage.remove(*paths)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
