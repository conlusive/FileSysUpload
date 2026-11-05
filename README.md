# File Upload Service

Серверний застосунок для **завантаження та обробки файлів** (file upload) — курсова робота.
Написаний на Python із використанням FastAPI. Надає REST API для автентифікованих користувачів:
приймає файли (`multipart/form-data`), перевіряє їх за реальним вмістом, обробляє зображення
(оптимізована копія та мініатюра), зберігає метадані в базі даних SQLite і віддає/видаляє файли.

## Можливості

- реєстрація та вхід, автентифікація за **JWT** (OAuth2 password flow), паролі хешуються **scrypt**;
- потокове читання завантаження порціями з обмеженням розміру (413) та раннім відхиленням за `Content-Length`;
- визначення типу за **сигнатурою** файлу (JPEG, PNG, GIF, WebP, PDF) і звірка з розширенням та `Content-Type` (415);
- обробка зображень (Pillow): виправлення EXIF-орієнтації, оптимізована копія (довша сторона ≤ 1600 px),
  мініатюра (≤ 256 px), стиснення, видалення метаданих; захист від «бомб розпакування»;
- метадані в БД: ім'я, тип, розмір, SHA-256, розміри зображення, власник, дата;
- список файлів із пагінацією, фільтром за типом і пошуком за ім'ям, скачування (оригінал / оптимізоване / мініатюра), видалення;
- кожен користувач бачить лише свої файли (чужі — 404);
- інтерактивна документація Swagger UI: `/docs`.

## Швидкий старт

Потрібен Python 3.11+ (перевірено на 3.13).

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.asgi:app --reload
```

Відкрийте <http://127.0.0.1:8000/docs>: зареєструйтесь (`POST /auth/register`), натисніть **Authorize**,
введіть логін і пароль та завантажте файл через `POST /files`.

Демонстраційний сценарій із командного рядка (сервер має працювати):

```bash
pip install httpx
python scripts/demo.py
```

## Тести

```bash
pip install -r requirements-dev.txt
pytest --cov=app
```

## Конфігурація

Налаштування читаються зі змінних середовища (див. `.env.example`).

| Змінна | Типове значення | Призначення |
|---|---|---|
| `SECRET_KEY` | небезпечне тестове | ключ підпису JWT — **обов'язково змініть** у реальному використанні |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | час життя токена |
| `DATABASE_URL` | `sqlite:///./data/app.db` | рядок підключення до БД |
| `STORAGE_DIR` | `./data/storage` | каталог для файлів |
| `MAX_UPLOAD_MB` | `10` | максимальний розмір файлу |
| `MAX_IMAGE_PIXELS` | `40000000` | максимальна кількість пікселів зображення |
| `OPTIMIZED_MAX_SIDE` / `THUMBNAIL_MAX_SIDE` | `1600` / `256` | розміри копій |
| `JPEG_QUALITY` | `85` | якість JPEG |

## API

| Метод і шлях | Опис |
|---|---|
| `GET /health` | перевірка працездатності |
| `POST /auth/register` | реєстрація (JSON: `username`, `password`) |
| `POST /auth/login` | вхід (form-data) → JWT |
| `GET /auth/me` | поточний користувач |
| `POST /files` | завантаження файлу (`multipart/form-data`, поле `file`) |
| `GET /files` | список: `limit`, `offset`, `kind`, `q` |
| `GET /files/{id}` | метадані файлу |
| `GET /files/{id}/download?variant=original\|optimized\|thumbnail` | скачування |
| `DELETE /files/{id}` | видалення |

## Структура

```
app/
  main.py          фабрика застосунку, middleware
  asgi.py          точка запуску для uvicorn
  config.py        налаштування
  database.py      підключення до БД
  models.py        ORM-моделі User, StoredFile
  schemas.py       Pydantic-схеми
  security.py      scrypt і JWT
  deps.py          залежності FastAPI
  errors.py        винятки
  routers/         auth.py, files.py
  services/        validation.py, images.py, storage.py
tests/             автоматичні тести (pytest)
scripts/demo.py    демонстраційний клієнт
```

## Обмеження

Файли зберігаються на диску одного сервера, відсутні CDN, відновлюване завантаження та антивірусна перевірка.
Для реального використання варто додати HTTPS (зворотний проксі), обмеження частоти запитів і міграції БД.
