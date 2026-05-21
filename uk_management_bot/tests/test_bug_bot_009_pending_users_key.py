"""
BUG-BOT-009: Raw localization key `user_management.pending_users` в UI.

После фикса ключ должен присутствовать в обоих локалях и не возвращаться
как литеральная строка из get_text().
"""
import pytest

from uk_management_bot.utils.helpers import get_text


class TestBugBot009PendingUsersKey:
    @pytest.mark.parametrize("language,expected_substring", [
        ("ru", "Новые жители"),
        ("uz", "Yangi aholilar"),
    ])
    def test_pending_users_translated(self, language, expected_substring):
        result = get_text("user_management.pending_users", language=language)
        assert result != "user_management.pending_users", (
            f"get_text вернул raw key для language={language}"
        )
        assert expected_substring in result, (
            f"Ожидалось '{expected_substring}' в '{result}'"
        )

    def test_pending_users_not_equal_raw_key_ru(self):
        assert get_text("user_management.pending_users", language="ru") \
            != "user_management.pending_users"

    def test_pending_users_not_equal_raw_key_uz(self):
        assert get_text("user_management.pending_users", language="uz") \
            != "user_management.pending_users"

    def test_other_list_type_keys_present(self):
        """Проверим parity для approved/blocked/staff/pending в обоих языках."""
        for language in ("ru", "uz"):
            for key in (
                "user_management.pending_users",
                "user_management.approved_users",
                "user_management.blocked_users",
                "user_management.staff_users",
            ):
                value = get_text(key, language=language)
                assert value != key, f"Missing translation: {key} ({language})"
