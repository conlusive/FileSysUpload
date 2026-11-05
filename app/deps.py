"""Залежності FastAPI: налаштування, сесія БД, сховище, поточний користувач."""
from __future__ import annotations

from collections.abc import Iterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.security import decode_access_token
from app.services.storage import FileStorage

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> FileStorage:
    return request.app.state.storage


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Повертає автентифікованого користувача за JWT або відповідає 401."""
    try:
        user_id = decode_access_token(token, settings)
    except (jwt.PyJWTError, ValueError):
        raise _CREDENTIALS_ERROR from None
    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_ERROR
    return user
