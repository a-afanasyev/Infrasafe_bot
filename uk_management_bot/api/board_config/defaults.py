"""Дефолтная конфигурация публичной витрины resident-board.

Воспроизводит текущий захардкоженный контент страницы (RU + UZ). Используется
сидером миграции 006 и как fallback в публичном эндпоинте, если строки нет.
"""
from uk_management_bot.config.settings import settings

# Идентификаторы перетаскиваемых модулей витрины. "workreports" зарезервирован
# для будущего модуля отчётов о выполненных работах (гейт — enabled_module_ids
# ниже) — до включения флага он не должен появляться в публичном ответе.
ALL_MODULE_IDS = ("stats", "requests", "announcements", "rating", "hours", "workreports")


def enabled_module_ids() -> tuple[str, ...]:
    """Модули, видимые снаружи при текущем состоянии settings.

    Пока WORK_REPORTS_ENABLED=False (дефолт везде) — "workreports" вырезается,
    даже если в БД для него уже есть строка layout (см. service.to_public_response).
    """
    if settings.WORK_REPORTS_ENABLED:
        return ALL_MODULE_IDS
    return tuple(m for m in ALL_MODULE_IDS if m != "workreports")


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
        {"id": "stats", "visible": True, "width": "full"},
        {"id": "requests", "visible": True, "width": "full"},
        {"id": "announcements", "visible": True, "width": "full"},
        {"id": "rating", "visible": True, "width": "half"},
        {"id": "hours", "visible": True, "width": "half"},
    ],
    # Настройки будущего модуля отчётов о выполненных работах (НЕ layout-запись —
    # та лежит в MODULE_DEFAULTS["workreports"] и бэкфиллится нормализатором).
    "work_reports": {
        "autopost": False,
        "autopost_since": None,
        "limit": 6,
        "title": {
            "ru": "Отчёты о выполненных работах",
            "uz": "Bajarilgan ishlar hisobotlari",
        },
    },
}

# Дефолт одной layout-записи на каждый известный модуль — используется
# нормализатором (schemas.StoredBoardConfigData._normalize_layout) для бэкфилла
# отсутствующих модулей. Первые 5 берём из DEFAULT_BOARD_CONFIG["layout"], чтобы
# не дублировать литералы; "workreports" — новый, deliberately invisible
# (visible=False) — появление нового модуля не должно менять то, что уже
# отрендерено на живой публичной странице, пока менеджер не включит его сам.
MODULE_DEFAULTS: dict[str, dict] = {item["id"]: dict(item) for item in DEFAULT_BOARD_CONFIG["layout"]}
MODULE_DEFAULTS["workreports"] = {"id": "workreports", "visible": False, "width": "full"}
