"""Утилиты для локализации адресов при отображении.

Адреса хранятся в БД в том виде, в котором были созданы (зависит от языка
пользователя на момент создания). Старые заявки содержат русские префиксы
("Дом: ", "Двор: ", "кв. ") даже при отображении на узбекском.

TODO: корневое решение — переход на структурированные адреса через
apartment_id → Apartment → Building → Yard с формированием отображения на лету.
"""

import re
from typing import Optional


def localize_address_error(err: Optional[str], language: str = "ru") -> str:
    """FE-094: локализовать ошибку address_service для бота.

    `err` — это либо стабильный код ошибки (set через `AddressError.code` или
    SQLAlchemy-ветку сервиса: `yard_not_found`, `save_failed`, …) → берётся из
    `address_errors.<code>` локали; либо уже готовое русское сообщение
    (интерполированный `AddressConflict` без кода) → возвращается как есть
    (fallback). Распознавание: `get_text` отдаёт сам ключ, если он не найден —
    значит это не код, а сообщение.
    """
    if not err:
        return ""
    from uk_management_bot.utils.helpers import get_text

    key = f"address_errors.{err}"
    text = get_text(key, language=language)
    return err if text == key else text


def localize_address(address: str, language: str) -> str:
    """Заменяет русские адресные префиксы на локализованные при отображении.

    BUG-BOT-012: использует i18n-строки `address.apartment_short` /
    `address.building_short` вместо хардкода "кв." / "д.".
    """
    if not address:
        return address

    if language == "ru":
        # RU: адрес уже в русском формате — отдаём как есть.
        # BUG-BOT-039: i18n-lookup'ы apt_short/bld_short нужны только UZ-ветке,
        # поэтому делаем их ПОСЛЕ этого short-circuit (раньше — безусловно,
        # dead work на каждом RU-рендере).
        return address

    # Импорт внутри функции, чтобы избежать циклов
    from uk_management_bot.utils.helpers import get_text

    apt_short = get_text("address.apartment_short", language=language)
    bld_short = get_text("address.building_short", language=language)

    # Префиксы — только в начале строки
    if address.startswith("Дом: "):
        address = "Uy: " + address[5:]
    elif address.startswith("Двор: "):
        address = "Hovli: " + address[6:]

    # "кв. 54" / "кв. 12А" → "54-{apartment_short}" (узбекский формат: значение
    # перед суффиксом). COD-09: apartment_number — freeform ("12А", "3/1"), не
    # только числа; расширяем класс до [\w/-]+ (как в building-ветке ниже).
    address = re.sub(
        r"кв\.\s*([\w/-]+)",
        lambda m: f"{m.group(1)}-{apt_short}",
        address,
    )

    # "д. 14" → "14-{building_short}." (узбекский формат)
    address = re.sub(
        r"\bд\.\s*([\w/-]+)",
        lambda m: f"{m.group(1)}-{bld_short}",
        address,
    )

    return address
