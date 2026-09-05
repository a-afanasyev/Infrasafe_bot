"""Чистое ядро сервиса «Лифты»: иерархия ошибок, DTO, канон-константы.

Без I/O. Здесь же ``StatusChange``/``Message`` — результат смены статуса
(``set_status`` появится в T3), чтобы обёртки не трогали этот файл.
"""

from dataclasses import dataclass
from datetime import datetime

# Канон категории заявки «лифт». Ключ совпадает с
# ``keyboards/requests.py::CATEGORY_KEYS["elevator"]``; сам модуль клавиатур
# сюда не импортируется (тянет aiogram и локали в чистое ядро) — паритет
# закреплён тестом test_validation::test_elevator_category_is_canonical_request_category.
ELEVATOR_CATEGORY = "elevator"


# ===========================================================================
# Ошибки (роутер мапит: Validation → 422, NotFound → 404, Conflict/State → 409)
# ===========================================================================

class ElevatorServiceError(Exception):
    """База ошибок сервиса лифтов."""


class ElevatorValidationError(ElevatorServiceError):
    """Некорректные входные данные (→ 422)."""


class ElevatorNotFoundError(ElevatorServiceError):
    """Лифт / запись графика не найдены (→ 404)."""


class ElevatorConflictError(ElevatorServiceError):
    """Нарушение инварианта: дубль места лифта, гонка версий и т.п. (→ 409)."""


class ElevatorStateError(ElevatorConflictError):
    """Недопустимый переход или состояние: архивный лифт, статус до ввода
    в эксплуатацию, правка завершённой записи графика (→ 409)."""


# ===========================================================================
# DTO
# ===========================================================================

@dataclass(frozen=True)
class Message:
    """Адресованное уведомление: кому (telegram_id) и готовый текст."""

    telegram_id: int
    text: str


@dataclass(frozen=True)
class StatusChange:
    """Результат ``set_status``: что изменилось и кого уведомить.

    ``changed=False`` — идемпотентный повтор того же статуса, сообщений нет.
    """

    changed: bool
    elevator_id: int
    old_status: str | None
    new_status: str | None
    status_since: datetime | None
    resident_messages: tuple[Message, ...] = ()
    staff_messages: tuple[Message, ...] = ()


# ===========================================================================
# Хелперы времени
# ===========================================================================

def require_aware(value: datetime, name: str) -> datetime:
    """Вернуть ``value``, если он tz-aware; naive → ``ValueError``.

    Правило репо: naive datetime никогда не сравниваются (ARCH-137).
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}: ожидается tz-aware datetime, получен naive")
    return value
