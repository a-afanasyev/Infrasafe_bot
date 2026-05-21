"""Утилиты для локализации адресов при отображении.

Адреса хранятся в БД в том виде, в котором были созданы (зависит от языка
пользователя на момент создания). Старые заявки содержат русские префиксы
("Дом: ", "Двор: ", "кв. ") даже при отображении на узбекском.

TODO: корневое решение — переход на структурированные адреса через
apartment_id → Apartment → Building → Yard с формированием отображения на лету.
"""

import re


def localize_address(address: str, language: str) -> str:
    """Заменяет русские адресные префиксы на локализованные при отображении.

    BUG-BOT-012: использует i18n-строки `address.apartment_short` /
    `address.building_short` вместо хардкода "кв." / "д.".
    """
    if not address:
        return address

    # Импорт внутри функции, чтобы избежать циклов
    from uk_management_bot.utils.helpers import get_text

    apt_short = get_text("address.apartment_short", language=language)
    bld_short = get_text("address.building_short", language=language)

    if language == "ru":
        # RU: нормализуем формат сокращений, если ключи определены явно
        # (на случай если в БД хранится альтернативный регистр/пробелы).
        return address

    # Префиксы — только в начале строки
    if address.startswith("Дом: "):
        address = "Uy: " + address[5:]
    elif address.startswith("Двор: "):
        address = "Hovli: " + address[6:]

    # "кв. 54" → "54-{apartment_short}." (узбекский формат: число перед суффиксом)
    address = re.sub(
        r"кв\.\s*(\d+)",
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
