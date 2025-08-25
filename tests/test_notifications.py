from uk_management_bot.services.notification_service import (
    build_role_switched_message,
    build_action_denied_message,
)


class DummyUser:
    def __init__(self, language: str = "ru"):
        self.language = language
        self.telegram_id = 123


def test_build_role_switched_message_ru():
    user = DummyUser(language="ru")
    msg = build_role_switched_message(user, "applicant", "executor")
    assert isinstance(msg, str)
    assert "Режим" in msg or "переключ" in msg.lower()


def test_build_role_switched_message_uz():
    user = DummyUser(language="uz")
    msg = build_role_switched_message(user, "applicant", "manager")
    assert isinstance(msg, str)
    # Сообщение на узбекском, но проверим, что не пустое
    assert len(msg) > 0


def test_build_action_denied_message_variants():
    ru = build_action_denied_message("not_in_shift", language="ru")
    assert "Действие" in ru

    uz = build_action_denied_message("permission_denied", language="uz")
    assert len(uz) > 0


