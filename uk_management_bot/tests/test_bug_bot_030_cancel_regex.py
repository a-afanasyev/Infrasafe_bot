"""
BUG-BOT-030: handler `handle_cancel_request` использовал prefix-match
(`F.data.startswith("cancel_")`) с поддерживаемым exclusion list —
открытое множество. Заменено на строгий regex `^cancel_\\d{6}-\\d{3}$`
по формату request_number (`YYMMDD-NNN`).

Test покрывает matching и non-matching пути.
"""
from __future__ import annotations

import re
import pytest


# Импортируем regex напрямую из handler-модуля
from uk_management_bot.handlers.requests import _CANCEL_REQUEST_NUMBER_RE


class TestBugBot030CancelRegex:
    @pytest.mark.parametrize("data", [
        "cancel_260520-001",
        "cancel_260521-099",
        "cancel_991231-999",
        "cancel_000101-000",
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
        "cancel_260520-1",  # короткий счётчик
        "cancel_260520-1234",  # длинный счётчик
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
        """Спецификация требует именно YYMMDD-NNN."""
        assert _CANCEL_REQUEST_NUMBER_RE.pattern == r"^cancel_\d{6}-\d{3}$"
