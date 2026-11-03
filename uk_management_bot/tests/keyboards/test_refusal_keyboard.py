"""Отказ одобрения в боте ведёт в дашборд (кейс profk id=93, 2026-11-03).

Документ жителя бот не показывает, проверка — только в дашборде, поэтому
отказ «сначала подтвердите верификацию» обязан нести URL-кнопку туда.
"""
import pytest

from uk_management_bot.keyboards.user_management import get_refusal_keyboard


@pytest.fixture
def frontend(monkeypatch):
    from uk_management_bot.config.settings import settings
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://profk.uz")


@pytest.mark.parametrize("refusal", ["verification_required", "property_document_required"])
def test_dashboard_button_for_document_refusals(frontend, refusal):
    kb = get_refusal_keyboard(refusal, 93, "ru")
    button = kb.inline_keyboard[0][0]
    assert button.url.startswith("https://profk.uz") and button.url.endswith("/93")


def test_no_button_for_phone_refusal(frontend):
    """Телефон в дашборде не исправить — житель делится контактом сам."""
    assert get_refusal_keyboard("phone_required", 93, "ru") is None


def test_no_button_without_frontend_url(monkeypatch):
    from uk_management_bot.config.settings import settings
    monkeypatch.setattr(settings, "FRONTEND_URL", "")
    assert get_refusal_keyboard("verification_required", 93, "ru") is None
