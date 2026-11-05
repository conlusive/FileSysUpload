"""ASGI-об'єкт для запуску: ``uvicorn app.asgi:app``."""
from app.main import create_app

app = create_app()  # pragma: no cover
