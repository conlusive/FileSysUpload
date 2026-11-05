"""Модульні тести допоміжних функцій: валідація, безпека, конфігурація."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import DEFAULT_SECRET, Settings
from app.security import hash_password, verify_password
from app.services.validation import (
    GIF, JPEG, PDF, PNG, WEBP,
    is_valid_file_id, sanitize_filename, sniff_type, validate_declared,
)
from tests.conftest import image_bytes, pdf_bytes


@pytest.mark.parametrize(
    "fmt,expected",
    [("JPEG", JPEG), ("PNG", PNG), ("GIF", GIF), ("WEBP", WEBP)],
)
def test_sniff_images(fmt, expected):
    assert sniff_type(image_bytes(fmt, (8, 8))[:32]) is expected


def test_sniff_pdf_and_unknown():
    assert sniff_type(pdf_bytes()[:32]) is PDF
    assert sniff_type(b"MZ\x90\x00 executable") is None
    assert sniff_type(b"<?php echo 1;") is None
    assert sniff_type(b"RIFF....WAVE") is None       # RIFF, але не WebP
    assert sniff_type(b"") is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("photo.jpg", "photo.jpg"),
        ("../../etc/passwd.png", "passwd.png"),
        ("C:\\Users\\x\\evil.png", "evil.png"),
        ("  spaced name .png ", "spaced name .png"),
        ("null\x00byte.png", "nullbyte.png"),
        ("tab\tand\nnewline.png", "tabandnewline.png"),
        ("", "file"),
        (None, "file"),
        ("...", "file"),
        ("звіт №1.pdf", "звіт №1.pdf"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_truncates_but_keeps_extension():
    name = sanitize_filename("a" * 400 + ".png")
    assert len(name) == 255 and name.endswith(".png")
    assert len(sanitize_filename("b" * 400)) == 255


def test_validate_declared_accepts_matching_and_generic():
    validate_declared(JPEG, "a.JPG", "image/jpeg")
    validate_declared(JPEG, "a.jpeg", "image/jpg")
    validate_declared(PNG, "a.png", "application/octet-stream")
    validate_declared(PDF, "a.pdf", None)
    validate_declared(PDF, "a.pdf", "application/pdf; charset=binary")


@pytest.mark.parametrize(
    "ft,name,ctype",
    [(PNG, "a.exe", "image/png"), (PNG, "noext", "image/png"), (PNG, "a.png", "image/jpeg"), (PDF, "a.png", "application/pdf")],
)
def test_validate_declared_rejects_mismatch(ft, name, ctype):
    with pytest.raises(HTTPException) as info:
        validate_declared(ft, name, ctype)
    assert info.value.status_code == 415


def test_is_valid_file_id():
    assert is_valid_file_id("a" * 32)
    assert not is_valid_file_id("../" + "a" * 29)
    assert not is_valid_file_id("A" * 32)


def test_password_hashing():
    first, second = hash_password("secret-password"), hash_password("secret-password")
    assert first != second                                # різна сіль
    assert verify_password("secret-password", first)
    assert not verify_password("Secret-password", first)
    assert first.startswith("scrypt$32768$8$3$")          # параметри за рекомендацією OWASP


@pytest.mark.parametrize("broken", ["", "plain", "md5$1$2$3$4$5", "scrypt$x$y$z$@@$@@", "scrypt$32768$8$3$AAAA"])
def test_verify_password_handles_malformed_hash(broken):
    assert verify_password("anything", broken) is False


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("MAX_UPLOAD_MB", "3")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "s"))
    s = Settings.from_env()
    assert s.max_upload_bytes == 3 * 1024 * 1024
    assert s.storage_dir == tmp_path / "s"
    assert not s.uses_default_secret
    monkeypatch.delenv("SECRET_KEY")
    assert Settings.from_env().secret_key == DEFAULT_SECRET


def test_sqlite_parent_directory_is_created(tmp_path):
    from app.database import make_engine

    nested = tmp_path / "a" / "b" / "app.db"
    engine = make_engine(f"sqlite:///{nested}")
    with engine.connect():
        pass
    assert nested.parent.is_dir()
    engine.dispose()
    assert make_engine("sqlite:///:memory:") is not None
