"""ASGI-проміжний шар, який обмежує розмір тіла запиту на завантаження."""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import too_large


class UploadBodyLimitMiddleware:
    """Рахує байти тіла POST /files під час приймання й обриває його на межі ліміту.

    Starlette розбирає multipart у тимчасовий файл ще до обробника, тому без цієї
    перевірки запит без Content-Length міг би заповнювати диск без обмежень.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int, max_file_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_file_bytes = max_file_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/files":
            await self.app(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise too_large(self.max_file_bytes)
            return message

        await self.app(scope, limited_receive, send)
