"""Единый предикат «есть ли у пользователя доступ к ЭТОЙ заявке» (П5, AUD3-14).

До этого модуля предикат существовал в ПЯТИ расходящихся формах, и расходились
они в обе стороны:

* `api/dependencies_access.check_request_access` — детали заявки в API/TWA:
  менеджер и владелец полный доступ, исполнитель только по `executor_id` и
  индивидуальному назначению, сосед по квартире только на «Исполнено».
  **Групповое назначение не учитывалось вовсе** (у групповых строк
  `RequestAssignment.executor_id` — NULL по определению), поэтому исполнитель
  видел заявку в списке и получал 403 при открытии.
* `api/requests/router.list_requests` — список в API: групповое назначение
  учитывается, но только при активной смене.
* `handlers/requests/listing.py` — детали в боте: **ветки менеджера нет вовсе**
  (менеджер открывал отчёт, жал «Назад к заявке» и упирался в «нет доступа»),
  роль читалась из `active_role` через `if/else`, из-за чего multi-role
  исполнитель с временно другой активной ролью терял доступ к своим
  назначениям; сосед пускался на заявку ЛЮБОГО статуса; групповое назначение
  учитывалось без условия про смену.
* `handlers/request_reports.py` — отчёт: менеджер и владелец есть, исполнитель
  только по `executor_id`, соседа нет.
* `utils/auth_helpers.has_executor_access` — отвечает на ДРУГОЙ вопрос
  («исполнитель ли пользователь вообще»), к конкретной заявке отношения не
  имеет; в проде ноль вызовов.

Канон (решение владельца 2026-07-27) — семантика API с двумя уточнениями:
сосед только на «Исполнено»; групповое назначение даёт доступ, но требует
активной смены (так это написано в списке API — единственном месте, где
правило сформулировано осознанно, с явным комментарием).

Ядро намеренно ЧИСТОЕ и работает над готовыми фактами: у бота синхронная
`Session`, у API — `AsyncSession`, и общей функции с вводом-выводом между ними
быть не может. Факты собирают тонкие адаптеры на каждой стороне, а решение
принимает только этот модуль — расхождение правил становится невозможным, а
расхождение сборщиков ловит parity-тест.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

from uk_management_bot.utils.specializations import matches_required_specs

#: Порядок правил канона. Служит и документацией, и опорой для тестов.
ACCESS_RULES = (
    "manager",
    "owner",
    "executor_direct",
    "executor_individual_assignment",
    "executor_group_assignment_on_shift",
    "apartment_resident_on_accepted",
)

#: Статус, на котором сосед по квартире получает доступ (флоу приёмки).
RESIDENT_ACCESS_STATUS = "Исполнено"


@dataclass(frozen=True)
class RequestAccessFacts:
    """Всё, что нужно знать о паре (пользователь, заявка), чтобы решить.

    Поля намеренно примитивные: ядро не должно уметь ходить в БД и не должно
    зависеть от того, ORM-объект перед ним или строка из другого сервиса.
    """

    roles: FrozenSet[str]
    user_id: int
    request_owner_id: Optional[int]
    request_executor_id: Optional[int]
    request_status: str
    request_apartment_id: Optional[int]
    #: Активное ИНДИВИДУАЛЬНОЕ назначение именно на этого пользователя.
    has_individual_assignment: bool
    #: Специализации активных ГРУППОВЫХ назначений этой заявки.
    group_specializations: FrozenSet[str]
    #: Специализации пользователя (канон-парсер `utils/specializations.py`).
    user_specializations: FrozenSet[str]
    has_active_shift: bool
    #: Одобренное соседство по квартире заявки (`UserApartment.status='approved'`).
    is_approved_resident: bool


def access_reason(facts: RequestAccessFacts) -> Optional[str]:
    """Первое сработавшее правило канона или None, если доступа нет.

    Возвращает именно ПРИЧИНУ, а не bool: по ней тесты и логи различают
    «пустил как менеджера» и «пустил как соседа», иначе регрессия вроде
    «менеджер проходит только потому, что он же и владелец» была бы незаметна.
    """
    if "manager" in facts.roles:
        return "manager"

    if facts.request_owner_id is not None and facts.request_owner_id == facts.user_id:
        return "owner"

    if "executor" in facts.roles:
        if facts.request_executor_id is not None and facts.request_executor_id == facts.user_id:
            return "executor_direct"
        if facts.has_individual_assignment:
            return "executor_individual_assignment"
        # Смена обязательна именно для группового назначения: его смысл —
        # «кто сейчас на дежурстве с этой специализацией», в отличие от
        # индивидуального, которое адресовано конкретному человеку.
        # BUG-168 (решение владельца 2026-08-19): канон BUG-166 и здесь —
        # `matches_required_specs` (universal-джокер с обеих сторон, одного
        # совпадения достаточно; расширение видимости универсалов одобрено).
        # Гвард на непустоту ОБЯЗАТЕЛЕН и не переносится в предикат: пустой
        # набор здесь значит «группового назначения нет», а не «требование
        # не ограничивает» (правило 1 канона сюда не относится). Сами
        # `group_specializations` приходят уже нормализованными — сбор в
        # `services/request_access.py`.
        if (
            facts.has_active_shift
            and facts.group_specializations
            and matches_required_specs(
                set(facts.user_specializations),
                set(facts.group_specializations),
            )
        ):
            return "executor_group_assignment_on_shift"

    if (
        facts.request_apartment_id is not None
        and facts.request_status == RESIDENT_ACCESS_STATUS
        and facts.is_approved_resident
    ):
        return "apartment_resident_on_accepted"

    return None


def has_request_access(facts: RequestAccessFacts) -> bool:
    """Булев ответ канона. Причину даёт `access_reason`."""
    return access_reason(facts) is not None


#: Булевы факты, каждый из которых может только ДОБАВИТЬ доступ.
#:
#: Все правила канона — положительные и соединены «или», поэтому предикат
#: монотонен по этим полям: переключение любого из False в True не способно
#: отобрать доступ. Свойство не косметическое — на нём стоит оптимизация
#: сборщиков фактов (`services/request_access.py`): сперва спрашиваем ядро по
#: дешёвым фактам, считая недостающие False, и лезем в БД только если доступа
#: не дали. Ложноположительный ответ так получить нельзя, ложноотрицательный
#: исправляет второй проход. Свойство закреплено тестом монотонности.
MONOTONE_BOOLEAN_FACTS = (
    "has_individual_assignment",
    "has_active_shift",
    "is_approved_resident",
)
