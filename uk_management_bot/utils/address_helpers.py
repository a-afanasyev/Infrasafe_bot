"""Утилиты для локализации адресов при отображении.

Адреса хранятся в БД в том виде, в котором были созданы (зависит от языка
пользователя на момент создания). Старые заявки содержат русские префиксы
("Дом: ", "Двор: ", "кв. ") даже при отображении на узбекском.

TODO: корневое решение — переход на структурированные адреса через
apartment_id → Apartment → Building → Yard с формированием отображения на лету.
"""

import re


def localize_address(address: str, language: str) -> str:
    """Заменяет русские адресные префиксы на локализованные при отображении."""
    if language == "ru" or not address:
        return address

    # Префиксы — только в начале строки
    if address.startswith("Дом: "):
        address = "Uy: " + address[5:]
    elif address.startswith("Двор: "):
        address = "Hovli: " + address[6:]

    # "кв. 54" → "54-xon." (узбекский формат: число перед суффиксом)
    address = re.sub(r"кв\.\s*(\d+)", r"\1-xon.", address)

    return address
