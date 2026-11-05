"""Спільні фікстури та допоміжні функції для тестів."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app

PASSWORD = "correct-horse-battery"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        secret_key="test-secret-key-0123456789-0123456789",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, username: str = "alice", password: str = PASSWORD) -> dict:
    response = client.post("/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def login_headers(client: TestClient, username: str = "alice", password: str = PASSWORD) -> dict[str, str]:
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    """Заголовки авторизації для користувача alice."""
    register(client, "alice")
    return login_headers(client, "alice")


@pytest.fixture
def auth_bob(client: TestClient) -> dict[str, str]:
    register(client, "bob")
    return login_headers(client, "bob")


def image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (800, 600), mode: str = "RGB", color=(40, 120, 200), **save_kwargs) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def pdf_bytes(size: int = 2048) -> bytes:
    body = b"%PDF-1.4\n% test document\n"
    return body + b"0" * max(0, size - len(body))


def upload(client: TestClient, headers: dict, name: str, data: bytes, content_type: str | None = None):
    files = {"file": (name, data, content_type) if content_type else (name, data)}
    return client.post("/files", files=files, headers=headers)


def storage_files(settings: Settings) -> list[Path]:
    """Усі файли у сховищі, крім каталогу тимчасових."""
    root = Path(settings.storage_dir).resolve()
    return sorted(p for p in root.rglob("*") if p.is_file() and ".tmp" not in p.parts)


def tmp_files(settings: Settings) -> list[Path]:
    tmp = Path(settings.storage_dir).resolve() / ".tmp"
    return sorted(p for p in tmp.glob("*") if p.is_file())
