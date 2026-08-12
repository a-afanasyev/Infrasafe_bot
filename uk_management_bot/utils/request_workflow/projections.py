"""Normalize (dual-read → канон) и проекции статуса наружу.

Block-move из utils/request_workflow.py (AUD5-ARCH-3 волна 10), тела
байт-в-байт.
"""

from __future__ import annotations

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
)

from .types import STATUS_RETURNED, RequestState

# ---------------------------------------------------------------------------
# Normalize — dual-read ДЛЯ РЕШЕНИЙ (обе legacy-кодировки → канон-статус)
# ---------------------------------------------------------------------------

def normalize_status(state: RequestState) -> str:
    """Канон-статус из legacy-кодировки.

    Telegram-композит: Выполнена+manager_confirmed (не возвращена) ⇒ Исполнено.
    Возврат (обе платформы пишут Исполнено+is_returned=True) ⇒ Возвращена.
    Прочее — как есть. После contract (PR4) функция вырождается в identity.
    """
    if state.status == REQUEST_STATUS_COMPLETED and state.is_returned:
        return STATUS_RETURNED
    if (state.status == REQUEST_STATUS_EXECUTED
            and state.manager_confirmed and not state.is_returned):
        return REQUEST_STATUS_COMPLETED
    return state.status


# ---------------------------------------------------------------------------
# Проекции наружу (PR0 Р3: «Возвращена» до обновления потребителей = Исполнено)
# ---------------------------------------------------------------------------

def project_public_status(state: RequestState) -> str:
    canon = normalize_status(state)
    return REQUEST_STATUS_COMPLETED if canon == STATUS_RETURNED else canon


def project_infrasafe_status(state: RequestState) -> str:
    # Пока InfraSafe не знает «Возвращена» — та же проекция (PR0 Р3/§5.5).
    return project_public_status(state)
