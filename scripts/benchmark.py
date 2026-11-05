"""Простий вимір швидкодії завантаження зображень різного розміру.

Запуск (сервер має працювати):  python scripts/benchmark.py [базова_адреса]
"""
from __future__ import annotations

import io
import random
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def photo(width: int, height: int, seed: int = 1) -> bytes:
    """Псевдо-фото: шум низької роздільної здатності, розтягнутий до потрібного розміру (реалістичний розмір JPEG)."""
    rnd = random.Random(seed)
    small = Image.new("RGB", (64, 48))
    small.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(64 * 48)])
    big = small.resize((width, height), Image.Resampling.BICUBIC)
    buffer = io.BytesIO()
    big.save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


def main() -> None:
    username = f"bench_{uuid.uuid4().hex[:6]}"
    with httpx.Client(base_url=BASE, timeout=120) as client:
        client.post("/auth/register", json={"username": username, "password": "bench-password-1"})
        token = client.post("/auth/login", data={"username": username, "password": "bench-password-1"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print("Одиночне завантаження (5 повторів, медіана):")
        print(f"{'Розмір, px':>14} {'Файл, КіБ':>10} {'Час, мс':>9} {'Оптим., КіБ':>12} {'Мініат., КіБ':>13}")
        for width, height in ((640, 480), (1280, 720), (1920, 1080), (4000, 3000)):
            data = photo(width, height)
            times, last = [], None
            for _ in range(5):
                start = time.perf_counter()
                response = client.post("/files", headers=headers, files={"file": ("bench.jpg", data, "image/jpeg")})
                times.append((time.perf_counter() - start) * 1000)
                assert response.status_code == 201, response.text
                last = response.json()
            print(f"{width:>6}x{height:<7} {len(data)/1024:>10.0f} {statistics.median(times):>9.0f} "
                  f"{last['optimized_size']/1024:>12.0f} {last['thumbnail_size']/1024:>13.1f}")

        data = photo(1920, 1080)
        def one(_: int) -> int:
            with httpx.Client(base_url=BASE, timeout=120) as c:
                return c.post("/files", headers=headers, files={"file": ("p.jpg", data, "image/jpeg")}).status_code

        print("\nОдночасні завантаження зображень 1920x1080:")
        for workers, total in ((1, 16), (4, 16), (8, 16)):
            start = time.perf_counter()
            with ThreadPoolExecutor(workers) as pool:
                codes = list(pool.map(one, range(total)))
            elapsed = time.perf_counter() - start
            print(f"потоків: {workers}, запитів: {total}, успішних: {codes.count(201)}, "
                  f"загальний час: {elapsed:.2f} с, пропускна здатність: {total/elapsed:.1f} запит/с")


if __name__ == "__main__":
    main()
