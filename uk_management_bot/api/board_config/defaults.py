"""Дефолтная конфигурация публичной витрины resident-board.

Воспроизводит текущий захардкоженный контент страницы (RU + UZ). Используется
сидером миграции 006 и как fallback в публичном эндпоинте, если строки нет.
"""

# Идентификаторы перетаскиваемых модулей витрины.
MODULE_IDS = ("stats", "requests", "announcements", "rating", "hours")

DEFAULT_BOARD_CONFIG = {
    "org": {
        "name": {
            "ru": "Управляющая компания",
            "uz": "Boshqaruv kompaniyasi",
        },
        "subtitle": {
            "ru": "ЖК Olmazor Business City · Информационное табло для жителей",
            "uz": "TJM Olmazor Business City · Aholilar uchun axborot tablosi",
        },
    },
    "contacts": {
        "dispatch_phone": "+998 71 123-45-67",
        "dispatch_label": {
            "ru": "Диспетчерская",
            "uz": "Dispetcherlik",
        },
        "emergency": {
            "ru": "Аварийная служба: круглосуточно",
            "uz": "Favqulodda xizmat: kunduzi-kechasi",
        },
    },
    "bot": {
        "username": "uk_management_bot",
        "label": {
            "ru": "Telegram-бот",
            "uz": "Telegram-bot",
        },
    },
    "announcements": [
        {
            "id": "default-planned-works",
            "icon": "⚠️",
            "important": True,
            "title": {
                "ru": "Плановые работы",
                "uz": "Rejalashtirilgan ishlar",
            },
            "text": {
                "ru": "промывка отопительной системы — 13 марта, 10:00–14:00",
                "uz": "isitish tizimini yuvish — 13 mart, 10:00–14:00",
            },
            "published_at": "2026-03-10T09:00:00",
        },
        {
            "id": "default-announcement",
            "icon": "\U0001F4E2",
            "important": False,
            "title": {
                "ru": "Объявления",
                "uz": "E'lonlar",
            },
            "text": {
                "ru": "",
                "uz": "",
            },
            "published_at": "2026-03-09T14:30:00",
        },
    ],
    "working_hours": [
        {"day": "mon", "open": "08:00", "close": "20:00", "closed": False},
        {"day": "tue", "open": "08:00", "close": "20:00", "closed": False},
        {"day": "wed", "open": "08:00", "close": "20:00", "closed": False},
        {"day": "thu", "open": "08:00", "close": "20:00", "closed": False},
        {"day": "fri", "open": "08:00", "close": "20:00", "closed": False},
        {"day": "sat", "open": "09:00", "close": "17:00", "closed": False},
        {"day": "sun", "open": "10:00", "close": "16:00", "closed": False},
    ],
    "layout": [
        {"id": "stats", "visible": True},
        {"id": "requests", "visible": True},
        {"id": "announcements", "visible": True},
        {"id": "rating", "visible": True},
        {"id": "hours", "visible": True},
    ],
}
