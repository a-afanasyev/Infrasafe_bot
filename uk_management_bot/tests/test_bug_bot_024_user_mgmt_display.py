"""
BUG-BOT-024: Double iconography в user-management views.

После фикса:
- `format_user_status('approved', 'ru')` → `✅ Одобрен` (без двойного эмодзи)
- detailed user info НЕ содержит подряд `✅ ✅` или `📊 📊`
- Если username отсутствует — выводится `Username не указан` (без `@`)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.employee_display import format_user_status


class TestBugBot024UserMgmtDisplay:
    @pytest.mark.parametrize("language,expected", [
        ("ru", "Username не указан"),
        ("uz", "Username ko'rsatilmagan"),
    ])
    def test_username_not_specified_localized(self, language: str, expected: str) -> None:
        result = get_text("user_mgmt.handlers.username_not_specified", language=language)
        assert result == expected
        assert "@" not in result

    @pytest.mark.parametrize("status,language", [
        ("approved", "ru"),
        ("approved", "uz"),
        ("pending", "ru"),
        ("blocked", "ru"),
    ])
    def test_format_user_status_single_emoji(self, status: str, language: str) -> None:
        result = format_user_status(status, language)
        # Не должно быть двух подряд эмодзи "✅ ✅"
        assert "✅ ✅" not in result
        assert "🚫 🚫" not in result
        assert "⏳ ⏳" not in result

    def test_detail_view_no_double_emoji_for_status(self) -> None:
        """Полная сборка строки detailed info не должна давать `✅ ✅`."""
        from uk_management_bot.services.user_management_service import UserManagementService

        user = MagicMock()
        user.id = 1
        user.telegram_id = 100
        user.first_name = "Иван"
        user.last_name = "Петров"
        user.username = None  # empty username path
        user.status = "approved"
        user.roles = '["applicant"]'
        user.role = "applicant"
        user.phone = None
        user.specialization = None

        svc = UserManagementService(db=MagicMock())
        info = svc.format_user_info(user, language="ru", detailed=True)

        # Не должно быть `@не указано`
        assert "@не указано" not in info
        # Должна быть локализованная подпись
        assert "Username не указан" in info
        # Никакого двойного `✅ ✅`
        assert "✅ ✅" not in info
        # status_text присутствует
        assert "Одобрен" in info
