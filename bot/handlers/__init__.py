"""Список всех обработчиков. Новый файл с обработчиками подключается одной строкой здесь."""

from bot.handlers import admin, menu, my_ads, post, report, search

ROUTERS = [
    menu.router,
    admin.router,
    search.router,
    my_ads.router,
    post.router,
    report.router,
]
