"""Запуск Mini App: python -m webapp.main"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from bot.config import load_settings
from bot.db import Database
from webapp.api import AppContext, router, validation_error_handler
from webapp.auth import RateLimiter

STATIC_DIR = Path(__file__).parent / "static"
# Слушаем только свой компьютер: наружу сервер выставляет HTTPS-туннель или прокси
HOST = "127.0.0.1"

# Что страница вправе загружать: свои файлы, скрипт Telegram и шрифты Google.
# frame-ancestors разрешает показ внутри Telegram (веб-версии открывают приложение во фрейме).
# Список, а не f-строка: по одному правилу на строку легче читать и менять
CONTENT_SECURITY_POLICY = "; ".join(  # noqa: FLY002
    [
        "default-src 'self'",
        "script-src 'self' https://telegram.org",
        "style-src 'self' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors https://*.telegram.org",
    ]
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if request.url.path.startswith("/api/"):
        # Ответы API личные (мои объявления), их нельзя хранить в кэше
        response.headers["Cache-Control"] = "no-store"
    return response


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    context: AppContext = app.state.ctx
    await context.db.init()
    yield
    await context.bot.session.close()


def create_app(context: AppContext) -> FastAPI:
    """Собирает приложение. Сборка отдельно от запуска, чтобы её можно было проверять тестами."""
    # Страницы документации отключены: они не нужны и показывали бы устройство API
    app = FastAPI(lifespan=_lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = context
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.middleware("http")(add_security_headers)
    app.include_router(router)
    # Статика подключается последней, иначе она перекрыла бы адреса API
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def main() -> None:
    settings = load_settings()
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    context = AppContext(settings, Database(settings.db_path), bot, RateLimiter())
    # access_log выключен: в адресах запросов бывает текст поиска, а его в логи писать нельзя
    uvicorn.run(create_app(context), host=HOST, port=settings.port, access_log=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
