"""Подписи лифта для бота и API: «{адрес дома}, подъезд N, лифт M» и имя статуса.

Локаль ``elevators.label`` / ``elevators.status.*`` (ru/uz); адрес дома проходит
``localize_address``, как в уведомлениях жителям. ``elevator_label`` требует
загруженного ``elevator.building`` (все выборки сервиса делают ``selectinload``).
Тексты НЕ экранированы для HTML — бот перед вставкой в HTML-сообщение обязан
применить ``html.escape``.
"""

from __future__ import annotations

from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES, Elevator
from uk_management_bot.utils.address_helpers import localize_address
from uk_management_bot.utils.helpers import get_text

from ._shared import DEFAULT_LANGUAGE

LABEL_KEY = "elevators.label"
STATUS_KEY_PREFIX = "elevators.status."


def status_label(status: str | None, language: str = DEFAULT_LANGUAGE) -> str:
    """Локализованное имя статуса лифта; ``None``/неизвестный → «не введён»."""
    key = status if status in ELEVATOR_STATUSES else "none"
    return get_text(STATUS_KEY_PREFIX + key, language=language)


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
