"""Р18: отказ самообслуживанию по лифту, на котором идут работы («В ремонте»/«На ТО»).

Один текст на три поверхности бота — личный поток жителя
(``create_elevator.py``), групповой приём (``group_intake_elevator.py``) и
подстраховка на подтверждении заявки (гонка: статус сменился между выбором
лифта и «Подтвердить»). Персонал (лифтёр, обходчик, колл-центр, InfraSafe)
сюда не попадает: у него ``allow_under_works=True`` в валидаторе Р18.

Р18a: сам запрет — тумблер менеджера
``elevators_config.allow_resident_requests_under_works`` (дефолт False =
запрещено). Тумблер включён → блока нет, остаётся прежняя мягкая подсказка;
поэтому «под работами» и «блокировать» здесь РАЗНЫЕ вопросы, и конфиг с
телефоном читаются только когда лифт действительно под работами.

Телефон диспетчера — из ``board_config`` через штатный
``RequestHandlerService.get_dispatch_phone`` (путь ``contacts.dispatch_phone``);
строка приходит из БД, поэтому в HTML-сообщение уходит только через
``html.escape``. Телефона нет → текст без него (отдельный ключ локали).

Лифт в тексте называется так же, как на остальных шагах заявки, — «подъезд N,
лифт M» (полный адресный ярлык ``elevators.label`` здесь избыточен: дом житель
только что выбрал сам).

DB-фаза — sync-юниты под ``run_db`` (гейт AUD3-37); данные наружу выходят
frozen-DTO, ORM за границу потока не выпускается.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from uk_management_bot.services.elevator_service import (
    ElevatorNotFoundError,
    get_elevator_including_archived_sync,
    is_under_works,
    load_config_sync,
    resident_requests_allowed,
    status_label,
)
from uk_management_bot.services.request_handler_service import RequestHandlerService
from uk_management_bot.utils.business_time import to_business
from uk_management_bot.utils.helpers import get_text

# Формат «идут работы с …» — как в прежней мягкой подсказке (T7).
SINCE_FORMAT = "%d.%m.%Y %H:%M"
SINCE_UNKNOWN = "—"

BLOCKED_KEY = "requests.elevator.works_blocked"
BLOCKED_NO_PHONE_KEY = "requests.elevator.works_blocked_no_phone"


@dataclass(frozen=True)
class WorksBlock:
    """Данные отказа: что за лифт, какие работы и куда звонить."""

    entrance: int
    number: int
    status: Optional[str]
    status_since: Optional[datetime]
    dispatch_phone: str = ""


def since_text(status_since: Optional[datetime]) -> str:
    """«01.09.2026 12:30» в бизнес-зоне; момент неизвестен → прочерк."""
    return f"{to_business(status_since):{SINCE_FORMAT}}" if status_since else SINCE_UNKNOWN


def works_blocked_text(block: WorksBlock, language: str) -> str:
    """Блокирующее сообщение жителю (HTML-безопасно: телефон экранирован)."""
    common = {
        "entrance": block.entrance,
        "elevator": block.number,
        "status": status_label(block.status, language),
        "since": since_text(block.status_since),
    }
    if not block.dispatch_phone:
        return get_text(BLOCKED_NO_PHONE_KEY, language=language, **common)
    return get_text(
        BLOCKED_KEY, language=language, phone=html.escape(block.dispatch_phone), **common
    )


def dispatch_phone_sync(db: Session) -> str:
    """Телефон диспетчера из board_config; строки нет → пусто."""
    return RequestHandlerService(db).get_dispatch_phone()


def works_blocked_sync(db: Session, status: Optional[str]) -> tuple[bool, str]:
    """``(блокировать ли, телефон диспетчера)`` для статуса лифта (Р18a).

    Ни конфиг, ни board_config не читаются, пока лифт не под работами, — на
    штатном пути лишних запросов нет.
    """
    if not is_under_works(status):
        return (False, "")
    if resident_requests_allowed(load_config_sync(db)):
        return (False, "")
    return (True, dispatch_phone_sync(db))


def works_block_sync(db: Session, elevator_id: int) -> Optional[WorksBlock]:
    """Лифт всё ещё под работами И запрет включён → данные отказа; иначе ``None``.

    Подстраховка на подтверждении: между выбором лифта и «Подтвердить» статус
    мог смениться. Неизвестный лифт — тоже ``None``: причина отказа другая,
    показываем общий текст.
    """
    try:
        elevator = get_elevator_including_archived_sync(db, elevator_id)
    except ElevatorNotFoundError:
        return None
    blocked, phone = works_blocked_sync(db, elevator.current_status)
    if not blocked:
        return None
    return WorksBlock(
        entrance=elevator.entrance_number,
        number=elevator.elevator_number,
        status=elevator.current_status,
        status_since=elevator.status_since,
        dispatch_phone=phone,
    )
