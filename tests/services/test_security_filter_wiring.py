"""E2 — проводка SecurityFilter и санитизация traceback (секревью PR IV).

Две регрессии, которые ловит файл:
* фильтр случайно вернули внутрь ветки `if not DEBUG` — маскирование снова
  живёт только в проде (E2);
* traceback из exc_info печатается форматтером сырьём мимо фильтра (паритет
  с TokenSanitizingFilter media-service).
"""
from __future__ import annotations

import logging

from uk_management_bot.utils.structured_logger import (
    SecurityFilter,
    setup_structured_logging,
)

TOKEN_URL = "https://api.telegram.org/bot12345:AAAAAAAAAAAAAAAAAAAAAAAAAAA/getFile"


def _root_has_security_filter() -> bool:
    root = logging.getLogger()
    return any(
        any(isinstance(f, SecurityFilter) for f in h.filters)
        for h in root.handlers
    )


def test_filter_wired_in_both_modes(monkeypatch):
    from uk_management_bot.config.settings import settings

    saved_handlers = logging.getLogger().handlers[:]
    try:
        for debug in (True, False):
            monkeypatch.setattr(settings, "DEBUG", debug)
            setup_structured_logging()
            assert _root_has_security_filter(), f"SecurityFilter потерян при DEBUG={debug}"
    finally:
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
        for h in saved_handlers:
            root.addHandler(h)


def test_traceback_is_sanitized_in_formatted_output():
    """Итоговая отформатированная запись (formatter.format с exc_info) без токена."""
    try:
        raise RuntimeError(f"Server error for url '{TOKEN_URL}'")
    except RuntimeError:
        import sys
        record = logging.LogRecord(
            "t", logging.ERROR, __file__, 1, "boom", (), sys.exc_info()
        )
    assert SecurityFilter().filter(record)
    out = logging.Formatter("%(message)s").format(record)
    assert "12345:AAAA" not in out
    assert "/bot[REDACTED]" in out
    assert "RuntimeError" in out  # traceback сохранён, вычищен только токен
