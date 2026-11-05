"""Тести реєстрації, входу та перевірки JWT."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import Settings
from app.security import create_access_token
from tests.conftest import PASSWORD, login_headers, register


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_register_success_does_not_leak_password(client):
    data = register(client, "Alice")
    assert data["username"] == "alice"            # нормалізація до нижнього регістру
    assert "password" not in data and "password_hash" not in data


def test_register_duplicate_is_case_insensitive(client):
    register(client, "alice")
    response = client.post("/auth/register", json={"username": "ALICE", "password": PASSWORD})
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ab", "password": PASSWORD},                 # занадто коротке ім'я
        {"username": "a" * 33, "password": PASSWORD},             # занадто довге ім'я
        {"username": "bad name!", "password": PASSWORD},          # недозволені символи
        {"username": "alice", "password": "short"},               # короткий пароль
        {"username": "alice", "password": "x" * 129},             # занадто довгий пароль
        {"username": "alice"},                                    # відсутній пароль
    ],
)
def test_register_validation_errors(client, payload):
    assert client.post("/auth/register", json=payload).status_code == 422


def test_login_success_and_me(client):
    register(client, "alice")
    response = client.post("/auth/login", data={"username": "Alice", "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["username"] == "alice"


@pytest.mark.parametrize("username,password", [("alice", "wrong-password"), ("nobody", PASSWORD)])
def test_login_wrong_credentials(client, username, password):
    register(client, "alice")
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_endpoints_require_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/files").status_code == 401
    assert client.post("/files", files={"file": ("a.pdf", b"%PDF-1")}).status_code == 401


def test_garbage_and_tampered_tokens_rejected(client, auth):
    assert client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    token = auth["Authorization"].split()[1]
    header, payload, signature = token.split(".")
    tampered = ".".join([header, payload, signature[:-2] + ("AA" if not signature.endswith("AA") else "BB")])
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_expired_token_rejected(client, settings: Settings):
    register(client, "alice")
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    token = create_access_token(1, settings, now=old)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_signed_with_other_key_rejected(client, settings: Settings):
    register(client, "alice")
    forged = jwt.encode({"sub": "1", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
                        "another-secret-key-0123456789-abcdef", algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_alg_none_token_rejected(client):
    register(client, "alice")
    b64 = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': '1', 'exp': exp})}."
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_without_exp_or_unknown_user_rejected(client, settings: Settings):
    register(client, "alice")
    no_exp = jwt.encode({"sub": "1"}, settings.secret_key, algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {no_exp}"}).status_code == 401
    ghost = create_access_token(9999, settings)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {ghost}"}).status_code == 401
    not_int = jwt.encode({"sub": "abc", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
                         settings.secret_key, algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {not_int}"}).status_code == 401


def test_login_helper_roundtrip(client):
    register(client, "carol")
    assert "Authorization" in login_headers(client, "carol")
