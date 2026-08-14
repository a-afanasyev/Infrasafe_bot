"""A4 / AUD5-ARCH-5 — global_error_handler логирует трейсбек САМОГО исключения.

Факт (проверен пробой на aiogram 3.30): ErrorsMiddleware зовёт error-хендлеры
внутри активного except-блока, поэтому в штатном polling-диспатче
traceback.format_exc() отдавал настоящий трейсбек. Дефект уже: лог зависел от
ambient exc-контекста ВЫЗЫВАЮЩЕГО — вне активного except (прямой вызов,
смена внутренностей aiogram) format_exc() печатает «NoneType: None», и
трейсбек юзерского исключения теряется. Канон: exc_info=event.exception —
печатает трейсбек именно того исключения, что несёт событие, всегда.
"""
import asyncio
import logging
from unittest.mock import MagicMock

from aiogram.types import Update

from uk_management_bot.main import global_error_handler


def _raise_deep_a4():
    raise ValueError("boom-a4")


def _make_error_event(exc: BaseException):
    """ErrorEvent с апдейтом без message/callback/inline — send-ветка не
    выполняется, тест изолирует ИМЕННО первую лог-строку."""
    from aiogram.types.error_event import ErrorEvent

    return ErrorEvent(update=Update(update_id=1), exception=exc)


def test_logs_traceback_of_event_exception_without_ambient_except(caplog):
    """Лог обязан содержать кадр места падения (независимо от exc-контекста
    вызывающего) и не должен деградировать в «NoneType: None»."""
    try:
        _raise_deep_a4()
    except ValueError as e:
        caught = e

    # Ключевой сценарий: вызов ВНЕ активного except-блока — ambient
    # exc-контекста нет, у format_exc() здесь нечего печатать.
    event = _make_error_event(caught)

    with caplog.at_level(logging.ERROR, logger="uk_management_bot.main"):
        result = asyncio.run(global_error_handler(event, bot=MagicMock()))

    assert result is True, "контракт aiogram «ошибка обработана» сохранён"
    assert "NoneType: None" not in caplog.text, (
        "в лог ушёл пустой ambient-контекст вместо трейсбека исключения"
    )
    assert "_raise_deep_a4" in caplog.text, (
        "в логе нет кадра места падения — трейсбек юзерского исключения потерян"
    )
