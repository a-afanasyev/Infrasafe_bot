"""Групповая приёмка заявок менеджером: ``MANAGER_CONFIRM`` по списку номеров.

Каждый номер — отдельная команда ``run_command_async`` (runner сам владеет
транзакцией и коммитит); отказ одной заявки (доменная ``WorkflowError``:
неверный переход, нет прав, не найдена…) фиксируется в результате и не
прерывает остальные. Иные исключения (инфраструктура) пробрасываются.
Post-commit intents (уведомления/realtime) возвращаются вызывающему — он
диспетчит их после ответа, как остальные адаптеры runner'а.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from uk_management_bot.services.workflow_runner import run_command_async
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    EventIntent,
    PrincipalRef,
    WorkflowError,
)

from ._core import ElevatorValidationError

MAX_BULK_CONFIRM = 50
DEFAULT_COMMAND_PREFIX = "bulk-confirm"


@dataclass(frozen=True)
class BulkItemResult:
    """Итог по одной заявке: ``ok`` либо ``error_kind``/``error`` (класс и текст WorkflowError)."""

    request_number: str
    ok: bool
    error_kind: str | None = None
    error: str | None = None
    post_commit_intents: tuple[EventIntent, ...] = ()


def _normalize_numbers(request_numbers: Sequence[str]) -> tuple[str, ...]:
    """Непустые строки без дублей, отсортированы; 1..MAX_BULK_CONFIRM штук."""
    if isinstance(request_numbers, (str, bytes)) or not isinstance(request_numbers, Sequence):
        raise ElevatorValidationError("request_numbers: ожидается список номеров заявок")
    cleaned = {number.strip() for number in request_numbers if isinstance(number, str) and number.strip()}
    if len(cleaned) != len(request_numbers):
        raise ElevatorValidationError("request_numbers: только непустые уникальные номера заявок")
    if not cleaned:
        raise ElevatorValidationError("request_numbers: список пуст")
    if len(cleaned) > MAX_BULK_CONFIRM:
        raise ElevatorValidationError(f"за один вызов не больше {MAX_BULK_CONFIRM} заявок")
    return tuple(sorted(cleaned))


async def bulk_confirm_async(
    session_factory,
    request_numbers: Sequence[str],
    *,
    principal: PrincipalRef,
    now: datetime | None = None,
    command_prefix: str = DEFAULT_COMMAND_PREFIX,
) -> tuple[BulkItemResult, ...]:
    """Последовательно подтвердить заявки (в порядке номеров); частичный сбой изолирован."""
    results: list[BulkItemResult] = []
    for number in _normalize_numbers(request_numbers):
        command = ActionCommand(
            command_id=f"{command_prefix}:{number}", action=Action.MANAGER_CONFIRM, payload={}
        )
        try:
            outcome = await run_command_async(session_factory, number, principal, command, now)
        except WorkflowError as exc:
            results.append(BulkItemResult(
                request_number=number, ok=False, error_kind=type(exc).__name__, error=str(exc),
            ))
            continue
        results.append(BulkItemResult(
            request_number=number, ok=True, post_commit_intents=tuple(outcome.post_commit_intents),
        ))
    return tuple(results)
