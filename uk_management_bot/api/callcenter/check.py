"""Проверка заявки по звонку перед отправкой (экран диспетчера).

«Тонкий ИИ»: модель только читает описание (тот же классификатор, что у
групп и подсказки адреса), а замечания выводят правила ниже. Замечание —
совет человеку, а не запрет: сбой модели даёт пустой список, заявку всё
равно можно отправить.
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.utils.constants import URGENCY_ORDER


@dataclass(frozen=True)
class Issue:
    """Замечание к полю формы. Текст — на клиенте по ``code`` (ru/uz)."""

    field: str
    code: str
    suggestion: Optional[str] = None
    options: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RequestCheck:
    ai_used: bool
    issues: tuple[Issue, ...] = ()


async def check_request(db: AsyncSession, *, description: str, category: str, urgency: str,
                        level: str, address_id: int) -> RequestCheck:
    from uk_management_bot.services.group_intake.classifier import Outcome, classify_message

    result = await classify_message(description)
    if result.outcome is Outcome.PROCESSING_ERROR:
        return RequestCheck(ai_used=False)
    if result.outcome is Outcome.NOT_REQUEST:
        return RequestCheck(ai_used=True, issues=(Issue("description", "description_unclear"),))

    issues: list[Issue] = []
    # Категорию и срочность оспариваем, только когда модель уверена — иначе
    # замечания превращаются в шум, и их перестают читать.
    if result.confidence >= settings.GROUP_INTAKE_MIN_CONFIDENCE:
        if result.category and result.category != category:
            issues.append(Issue("category", "category_mismatch", suggestion=result.category))
        # Только в сторону повышения: завышенная срочность — решение человека.
        if result.urgency and URGENCY_ORDER.get(result.urgency, 0) > URGENCY_ORDER.get(urgency, 0):
            issues.append(Issue("urgency", "urgency_low", suggestion=result.urgency))
    issues.extend(await _address_issues(db, result.location_scope, result.address_hint, level, address_id))
    return RequestCheck(ai_used=True, issues=tuple(issues))


async def _address_issues(db: AsyncSession, scope: str, hint: Optional[str],
                          level: str, address_id: int) -> list[Issue]:
    from uk_management_bot.api.callcenter.service import _match_directory

    issues: list[Issue] = []
    if hint:
        # Ищем только по адресу, названному в тексте: цифры из остального
        # описания («течёт 2 дня») адресом не считаем.
        options = await db.run_sync(_match_directory, scope, hint, "")
        if options and not _chosen_among(options, *await _chosen_yard_building(db, level, address_id)):
            issues.append(Issue("address", "address_mismatch", options=tuple(options)))
    if scope == "apartment" and level != "apartment":
        issues.append(Issue("address", "apartment_expected"))
    return issues


async def _chosen_yard_building(db: AsyncSession, level: str,
                                address_id: int) -> tuple[Optional[int], Optional[int]]:
    """(двор, дом) выбранного адреса; дом — None для уровня «двор»."""
    if level == "yard":
        return address_id, None
    building_id: Optional[int] = address_id
    if level == "apartment":
        apartment = await db.get(Apartment, address_id)
        building_id = apartment.building_id if apartment else None
    building = await db.get(Building, building_id) if building_id is not None else None
    return (building.yard_id, building.id) if building else (None, None)


def _chosen_among(options: list[dict], yard_id: Optional[int], building_id: Optional[int]) -> bool:
    if yard_id is None:
        # Адреса нет в справочнике — это отобьёт создание заявки (422), не мы.
        return True
    return any(
        (o["type"] == "building" and o["id"] == building_id) or (o["type"] == "yard" and o["id"] == yard_id)
        for o in options
    )
