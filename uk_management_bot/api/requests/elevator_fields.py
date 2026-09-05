"""Поля лифта на ``RequestCard`` (Ф4a-1): подпись и статус — без N+1.

Один batch-запрос лифтов (с домами) на страницу карточек; подпись — единая
``elevator_label`` из домена. Используется роутерами заявок и колл-центра.
Никакого relationship на ``Request``: в async-сессии lazy-load невозможен,
явный словарь ``{id: Elevator}`` не даёт случайно наступить на него.

``PersistedRequest`` — результат create-сервисов: заявка + лифт, уже
загруженный валидатором Р11 (повторного запроса для ответа POST нет).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.requests.schemas import RequestCard
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.elevator_service import (
    elevator_label,
    get_elevators_by_ids_async,
)

DEFAULT_LANGUAGE = "ru"


@dataclass(frozen=True)
class PersistedRequest:
    """Свежесозданная заявка и её лифт (``None``, если не привязан)."""

    request: Request
    elevator: Elevator | None


def card_language(user) -> str:
    """Язык подписи лифта — язык пользователя API (``ru`` по умолчанию)."""
    return getattr(user, "language", None) or DEFAULT_LANGUAGE


async def load_elevators(db: AsyncSession, requests: Iterable) -> dict[int, Elevator]:
    """``{elevator_id: Elevator}`` для набора заявок одним запросом (пусто — без запроса)."""
    ids = {r.elevator_id for r in requests if r.elevator_id is not None}
    return await get_elevators_by_ids_async(db, ids)


def attach_elevator(card: RequestCard, elevator: Elevator | None, language: str) -> RequestCard:
    """Новая карточка с ``elevator_label``/``elevator_status``; без лифта — та же карточка."""
    if elevator is None:
        return card
    return card.model_copy(update={
        "elevator_label": elevator_label(elevator, language),
        "elevator_status": elevator.current_status,
    })


def persisted_card(persisted: PersistedRequest, *, language: str) -> RequestCard:
    """Карточка ответа POST: заявка + поля лифта из ``PersistedRequest``."""
    return attach_elevator(
        RequestCard.model_validate(persisted.request), persisted.elevator, language
    )
