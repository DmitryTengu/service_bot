"""Методы API Mini App. Все права проверяются здесь, на сервере, а не на странице."""

import re
from dataclasses import dataclass
from typing import Annotated

from aiogram import Bot
from aiogram.types import User
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from bot import keyboards, texts
from bot.categories import CATEGORIES, get_category
from bot.config import MAX_LIVE_ADS, Settings
from bot.db import ACTIVE, PENDING, Database, LimitReached, page_count
from bot.notify import notify_admins
from webapp.auth import (
    AuthError,
    RateLimiter,
    TelegramUser,
    is_member,
    validate_init_data,
)
from webapp.schemas import (
    CategoryOut,
    CreatedOut,
    ListingIn,
    ListingOut,
    ListingsPage,
    MyListingOut,
)

MAX_QUERY_LENGTH = 60
MAX_PAGE = 10_000
MAX_LISTING_ID = 2**31
AUTH_SCHEME = "tma"
# Так выглядят настоящие @username в Telegram; всё остальное в ссылку не превращаем
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{4,32}$")
_VALUE_ERROR_PREFIX = "Value error, "

LIMIT_MESSAGE = f"Достигнут лимит объявлений: {MAX_LIVE_ADS}. Скройте или удалите одно."

router = APIRouter(prefix="/api")


@dataclass
class AppContext:
    """Всё, что нужно методам: настройки, база, бот для уведомлений и счётчик запросов."""

    settings: Settings
    db: Database
    bot: Bot
    limiter: RateLimiter


def get_context(request: Request) -> AppContext:
    return request.app.state.ctx


ContextDep = Annotated[AppContext, Depends(get_context)]
ListingId = Annotated[int, Path(ge=1, le=MAX_LISTING_ID)]


async def current_user(
    ctx: ContextDep, authorization: Annotated[str | None, Header()] = None
) -> TelegramUser:
    """Пользователь из проверенной initData. Номер берётся только отсюда, не из запроса."""
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != AUTH_SCHEME or not init_data:
        raise HTTPException(401, "Откройте приложение из Telegram.")
    try:
        user = validate_init_data(init_data, ctx.settings.bot_token)
    except AuthError:
        raise HTTPException(401, "Не удалось проверить вас. Откройте приложение заново.") from None
    if not await is_member(user.id):
        raise HTTPException(403, "Доступ закрыт.")
    if not ctx.limiter.allow(user.id):
        raise HTTPException(429, "Слишком много запросов. Подождите минуту.")
    return user


UserDep = Annotated[TelegramUser, Depends(current_user)]


def _not_found() -> HTTPException:
    return HTTPException(404, "Объявление не найдено.")


def _contact_url(username: str | None) -> str | None:
    """Ссылка на чат с автором; без @username её нет."""
    if username and _USERNAME_PATTERN.match(username):
        return f"https://t.me/{username}"
    return None


def _listing_fields(ad: dict) -> dict:
    category = get_category(ad["category"])
    return {
        "id": ad["id"],
        "category": ad["category"],
        "category_title": category.title if category else ad["category"],
        "title": ad["title"],
        "description": ad["description"],
        "price": ad["price"],
        "location": ad["location"],
        "phone": ad["phone"],
        "author_name": ad["author_name"] or "",
        "author_username": ad["author_username"],
        "contact_url": _contact_url(ad["author_username"]),
    }


def _my_listing(ad: dict) -> MyListingOut:
    return MyListingOut(**_listing_fields(ad), status=ad["status"])


async def validation_error_handler(request: Request, error: RequestValidationError):
    """Единый вид ошибок {"detail": "..."}; текст самого ввода в ответ не попадает."""
    message = "Проверьте введённые данные."
    for item in error.errors():
        if item["type"] == "value_error":
            message = str(item["msg"]).removeprefix(_VALUE_ERROR_PREFIX)
            break
    return JSONResponse({"detail": message}, status_code=422)


# ---------- каталог ----------


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories():
    return [CategoryOut(key=category.key, title=category.title) for category in CATEGORIES]


@router.get("/listings", response_model=ListingsPage)
async def list_listings(
    _: UserDep,
    ctx: ContextDep,
    category: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH)] = None,
    page: Annotated[int, Query(ge=0, le=MAX_PAGE)] = 0,
):
    if category and get_category(category) is None:
        raise HTTPException(422, "Такой категории нет.")
    ads, total = await ctx.db.search(category or None, (q or "").strip() or None, page)
    items = [ListingOut(**_listing_fields(ad)) for ad in ads]
    return ListingsPage(items=items, total=total, page=page, pages=page_count(total))


@router.get("/listings/{ad_id}", response_model=ListingOut)
async def get_listing(ad_id: ListingId, _: UserDep, ctx: ContextDep):
    ad = await ctx.db.get_ad(ad_id)
    if ad is None or ad["status"] != ACTIVE:
        raise _not_found()
    return ListingOut(**_listing_fields(ad))


@router.post("/listings", status_code=201, response_model=CreatedOut)
async def create_listing(body: ListingIn, user: UserDep, ctx: ContextDep):
    await ctx.db.save_user(user.id, user.username, user.first_name)
    fields = {**body.model_dump(), "phone": None}
    auto_approve = ctx.settings.auto_approve
    try:
        ad_id = await ctx.db.create_ad(user.id, fields, auto_approve)
    except LimitReached:
        raise HTTPException(409, LIMIT_MESSAGE) from None
    if not auto_approve:
        ad = await ctx.db.get_ad(ad_id)
        markup = keyboards.moderation(ad_id)
        await notify_admins(ctx.bot, ctx.settings, texts.ad_for_review(ad), markup)
    return CreatedOut(id=ad_id, status=ACTIVE if auto_approve else PENDING)


@router.post("/listings/{ad_id}/report", status_code=204)
async def report_listing(ad_id: ListingId, user: UserDep, ctx: ContextDep):
    ad = await ctx.db.get_ad(ad_id)
    if ad is None or ad["status"] != ACTIVE:
        raise _not_found()
    if not await ctx.db.add_report(user.id, ad_id):
        raise HTTPException(409, "Вы уже жаловались на это объявление.")
    reporter = User(id=user.id, is_bot=False, first_name=user.first_name, username=user.username)
    await notify_admins(ctx.bot, ctx.settings, texts.report_for_admin(ad, reporter))
    return Response(status_code=204)


# ---------- мои объявления ----------


@router.get("/my/listings", response_model=list[MyListingOut])
async def my_listings(user: UserDep, ctx: ContextDep):
    return [_my_listing(ad) for ad in await ctx.db.list_by_user(user.id)]


async def _set_hidden(ad_id: int, user: TelegramUser, ctx: AppContext, hidden: bool):
    """Общая часть «скрыть» и «показать»; правила в Database.set_hidden."""
    try:
        ad = await ctx.db.set_hidden(ad_id, user.id, hidden)
    except LimitReached:
        raise HTTPException(409, LIMIT_MESSAGE) from None
    if ad is None:
        raise _not_found()
    return _my_listing(ad)


@router.post("/my/listings/{ad_id}/hide", response_model=MyListingOut)
async def hide_listing(ad_id: ListingId, user: UserDep, ctx: ContextDep):
    return await _set_hidden(ad_id, user, ctx, hidden=True)


@router.post("/my/listings/{ad_id}/show", response_model=MyListingOut)
async def show_listing(ad_id: ListingId, user: UserDep, ctx: ContextDep):
    return await _set_hidden(ad_id, user, ctx, hidden=False)


@router.delete("/my/listings/{ad_id}", status_code=204)
async def delete_listing(ad_id: ListingId, user: UserDep, ctx: ContextDep):
    # Удаление только своих: owner_id берётся из проверенной подписи
    if not await ctx.db.delete_ad(ad_id, owner_id=user.id):
        raise _not_found()
    return Response(status_code=204)
