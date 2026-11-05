"""Реєстрація, вхід і профіль користувача."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.deps import get_current_user, get_db, get_settings
from app.models import User
from app.schemas import TokenOut, UserCreate, UserOut
from app.security import DUMMY_HASH, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Створює нового користувача. Ім'я нормалізується до нижнього регістру."""
    if db.scalar(select(User).where(User.username == payload.username)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username is already taken.")
    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # гонка двох одночасних реєстрацій
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username is already taken.") from None
    return user


@router.post("/login", response_model=TokenOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    """Видає JWT за логіном і паролем (OAuth2 password flow, form-data)."""
    user = db.scalar(select(User).where(User.username == form.username.lower()))
    # Хеш перевіряється завжди, щоб не розкривати існування логіну за часом відповіді.
    password_ok = verify_password(form.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenOut(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    """Повертає дані поточного користувача."""
    return user
