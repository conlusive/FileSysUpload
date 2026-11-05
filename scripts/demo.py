"""Демонстраційний клієнт: проходить увесь сценарій роботи із запущеним сервером.

Запуск (сервер має працювати на http://127.0.0.1:8000):
    python scripts/demo.py [базова_адреса]
"""
from __future__ import annotations

import io
import sys
import uuid

import httpx
from PIL import Image, ImageDraw

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def make_photo() -> bytes:
    """Генерує тестове зображення 3000x2000 із градієнтом і написом."""
    image = Image.new("RGB", (3000, 2000))
    draw = ImageDraw.Draw(image)
    for x in range(3000):
        draw.line([(x, 0), (x, 2000)], fill=(x * 255 // 3000, 120, 255 - x * 255 // 3000))
    draw.text((100, 100), "demo photo 3000x2000", fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95)
    return buffer.getvalue()


def show(title: str, response: httpx.Response) -> None:
    print(f"\n=== {title}\n{response.request.method} {response.request.url.path} -> {response.status_code}")
    content_type = response.headers.get("content-type", "")
    print(response.json() if "json" in content_type else f"[{content_type}, {len(response.content)} bytes]")


def main() -> None:
    username = f"demo_{uuid.uuid4().hex[:6]}"
    with httpx.Client(base_url=BASE, timeout=30) as client:
        show("Перевірка працездатності", client.get("/health"))
        show("Реєстрація", client.post("/auth/register", json={"username": username, "password": "demo-password-1"}))
        token = client.post("/auth/login", data={"username": username, "password": "demo-password-1"})
        show("Вхід (JWT)", token)
        headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

        photo = make_photo()
        uploaded = client.post("/files", headers=headers, files={"file": ("holiday.jpg", photo, "image/jpeg")})
        show("Завантаження зображення", uploaded)
        file_id = uploaded.json()["id"]

        for variant in ("original", "optimized", "thumbnail"):
            response = client.get(f"/files/{file_id}/download", params={"variant": variant}, headers=headers)
            size = Image.open(io.BytesIO(response.content)).size
            print(f"\n=== Скачування ({variant}): {response.status_code}, {len(response.content)} байтів, {size[0]}x{size[1]}")

        fake = client.post("/files", headers=headers, files={"file": ("fake.png", b"this is not an image", "image/png")})
        show("Підроблений файл (текст із розширенням .png)", fake)

        show("Список файлів", client.get("/files", headers=headers, params={"limit": 5}))
        show("Видалення", client.delete(f"/files/{file_id}", headers=headers))
        show("Повторне отримання після видалення", client.get(f"/files/{file_id}", headers=headers))


if __name__ == "__main__":
    main()
