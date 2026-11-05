"""Хешування паролів (scrypt) та робота з JWT."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.config import Settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_DKLEN = 32


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    """Повертає рядок формату ``scrypt$N$r$p$salt$hash`` (випадкова сіль на кожен пароль)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Перевіряє пароль у сталий час; некоректний формат хешу трактується як помилка перевірки."""
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


# Хеш-«пустушка»: перевіряється, коли користувача не знайдено, щоб час відповіді не видавав існування логіну.
DUMMY_HASH = hash_password("dummy-password-for-timing")


def create_access_token(user_id: int, settings: Settings, now: datetime | None = None) -> str:
    """Створює підписаний JWT із полями sub, iat та exp."""
    now = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str, settings: Settings) -> int:
    """Повертає id користувача або кидає ``jwt.PyJWTError`` / ``ValueError``."""
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
        options={"require": ["sub", "exp"]},
    )
    return int(payload["sub"])
