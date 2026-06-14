"""
BUG-BOT-030: handler `handle_cancel_request` использовал prefix-match
(`F.data.startswith("cancel_")`) с поддерживаемым exclusion list —
открытое множество. Заменено на строгий regex по формату request_number.

BUG-122: счётчик — 3+ цифры (`^cancel_\\d{6}-\\d{3,}$`), чтобы здания с
>999 заявок/день (`260520-1000`) тоже матчились. Матчер собран из shared
REQUEST_NUMBER_CORE.

Test покрывает matching и non-matching пути.
"""
from __future__ import annotations

import pytest


# Импортируем regex напрямую из handler-модуля
from uk_management_bot.handlers.requests import _CANCEL_REQUEST_NUMBER_RE


class TestBugBot030CancelRegex:
    @pytest.mark.parametrize("data", [
        "cancel_260520-001",
        "cancel_260521-099",
        "cancel_991231-999",
        "cancel_000101-000",
        "cancel_260520-1000",   # BUG-122: 4-digit rollover (>999/day)
        "cancel_991231-12345",  # BUG-122: 5-digit
    ])
    def test_matches_request_number_format(self, data: str) -> None:
        assert _CANCEL_REQUEST_NUMBER_RE.match(data) is not None

    @pytest.mark.parametrize("data", [
        # Старые ложно-положительные кейсы из exclusion list
        "cancel_document_selection_42",
        "cancel_plan_weekly_2026",
        "cancel_auto_plan_42",
        "cancel_action",
        "cancel_apartment_selection",
        # Произвольные опечатки
        "cancel_123",
        "cancel_abc-def",
        "cancel_2605-001",  # короткий формат даты
        "cancel_260520-1",  # счётчик <3 цифр
        "cancel_260520-12",  # счётчик <3 цифр
        "cancel_create",
        # Без префикса cancel_
        "260520-001",
        "",
    ])
    def test_does_not_match_non_request_callbacks(self, data: str) -> None:
        assert _CANCEL_REQUEST_NUMBER_RE.match(data) is None, (
            f"Regex unexpectedly matched: {data!r}"
        )

    def test_pattern_literal_matches_spec(self) -> None:
        """Спецификация требует YYMMDD-NNN с 3+ цифрами счётчика (BUG-122)."""
        assert _CANCEL_REQUEST_NUMBER_RE.pattern == r"^cancel_\d{6}-\d{3,}$"
