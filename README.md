# File Upload Service

A server application for **uploading and processing files** (coursework project).
Written in Python with FastAPI. It provides a REST API for authenticated users: it accepts files
(`multipart/form-data`), validates them by their real content, processes images
(an optimized copy and a thumbnail), stores metadata in a SQLite database, and serves/deletes files.

## Features

- registration and login, **JWT** authentication (OAuth2 password flow), passwords hashed with **scrypt**;
- streaming upload read in chunks with a size limit (413) and early rejection by `Content-Length`;
- file type detection by **signature** (JPEG, PNG, GIF, WebP, PDF), cross-checked against the extension and `Content-Type` (415);
- image processing (Pillow): EXIF orientation fix, optimized copy (long side ≤ 1600 px),
  thumbnail (≤ 256 px), compression, metadata stripping; protection against decompression bombs;
- metadata in the database: name, type, size, SHA-256, image dimensions, owner, date;
- file listing with pagination, type filter and name search; download (original / optimized / thumbnail); deletion;
- every user sees only their own files (other users' files return 404);
- interactive Swagger UI documentation at `/docs`.

## Quick start

Requires Python 3.11+ (tested on 3.13).

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.asgi:app --reload
```

Open <http://127.0.0.1:8000/docs>: register (`POST /auth/register`), click **Authorize**,
enter your username and password, then upload a file via `POST /files`.

Command-line demo scenario (the server must be running):

```bash
pip install httpx
python scripts/demo.py
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest --cov=app
```

## Configuration

Settings are read from environment variables (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | insecure development value | JWT signing key — **you must change it** for real use |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | token lifetime |
| `DATABASE_URL` | `sqlite:///./data/app.db` | database connection string |
| `STORAGE_DIR` | `./data/storage` | directory for stored files |
| `MAX_UPLOAD_MB` | `10` | maximum file size |
| `MAX_IMAGE_PIXELS` | `40000000` | maximum number of pixels in an image |
| `OPTIMIZED_MAX_SIDE` / `THUMBNAIL_MAX_SIDE` | `1600` / `256` | sizes of the generated copies |
| `JPEG_QUALITY` | `85` | JPEG quality |

## API

| Method and path | Description |
|---|---|
| `GET /health` | health check |
| `POST /auth/register` | register (JSON: `username`, `password`) |
| `POST /auth/login` | log in (form data) → JWT |
| `GET /auth/me` | current user |
| `POST /files` | upload a file (`multipart/form-data`, field `file`) |
| `GET /files` | list: `limit`, `offset`, `kind`, `q` |
| `GET /files/{id}` | file metadata |
| `GET /files/{id}/download?variant=original\|optimized\|thumbnail` | download |
| `DELETE /files/{id}` | delete |

## Project structure

```
app/
  main.py          application factory, middleware
  asgi.py          entry point for uvicorn
  config.py        settings
  database.py      database connection
  models.py        ORM models User, StoredFile
  schemas.py       Pydantic schemas
  security.py      scrypt and JWT
  deps.py          FastAPI dependencies
  errors.py        exceptions
  routers/         auth.py, files.py
  services/        validation.py, images.py, storage.py
tests/             automated tests (pytest)
scripts/demo.py    demo client
```

## Limitations

Files are stored on the disk of a single server; there is no CDN, resumable upload or antivirus scanning.
For real-world use, add HTTPS (reverse proxy), rate limiting and database migrations.
