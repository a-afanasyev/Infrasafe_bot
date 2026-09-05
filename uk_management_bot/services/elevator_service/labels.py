"""Подпись лифта «{адрес дома}, подъезд N, лифт M» — одна функция для бота и API.

Локаль ``elevators.label`` (ru/uz); адрес дома проходит ``localize_address``,
как в уведомлениях жителям. Требует загруженного ``elevator.building``
(все выборки сервиса делают ``selectinload``). Текст НЕ экранирован для HTML —
бот перед вставкой в HTML-сообщение обязан применить ``html.escape``.
"""

from __future__ import annotations

from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.utils.address_helpers import localize_address
from uk_management_bot.utils.helpers import get_text

from ._shared import DEFAULT_LANGUAGE

LABEL_KEY = "elevators.label"


def elevator_label(elevator: Elevator, language: str = DEFAULT_LANGUAGE) -> str:
    """Человеческая подпись лифта на языке ``language`` (``ru`` по умолчанию)."""
    address = localize_address(elevator.building.address or "", language)
    return get_text(
        LABEL_KEY,
        language=language,
        building=address,
        entrance=elevator.entrance_number,
        elevator=elevator.elevator_number,
    )
