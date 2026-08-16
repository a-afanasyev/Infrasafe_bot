"""Причину возврата должны увидеть исполнитель и житель (решение владельца).

Мало сохранить её в колонку: до этой правки уведомление о возврате было общим
для возврата менеджером и возврата жителем («заявка возвращена в работу») и
причины не несло, а `format_request_details` — единственный рендер карточки для
всех ролей в боте — про новое поле не знал.

Причина жителя (`return_reason`) и причина менеджера (`manager_return_reason`)
показываются РАЗНЫМИ подписями: это разные реплики одного диалога, и слипшись
они бы дезинформировали.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from uk_management_bot.utils.request_helpers import format_request_details


def _request(**overrides):
    base = dict(
        request_number="260817-001",
        category="elevator",
        status="В работе",
        address="Дом 1",
        description="Не работает лифт",
        urgency="Обычная",
        apartment=None,
        created_at=datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        executor_id=None,
        media_files=None,
        return_reason=None,
        manager_return_reason=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestCardRendering:
    def test_manager_reason_is_shown(self):
        text = format_request_details(
            _request(manager_return_reason="Плитка положена криво"), language="ru")

        assert "Плитка положена криво" in text

    def test_absent_reason_adds_nothing(self):
        text = format_request_details(_request(), language="ru")

        assert "Плитка" not in text
        # Блок опционален — у обычной заявки лишних пустых строк быть не должно.
        assert "\n\n\n" not in text

    def test_both_reasons_are_distinguishable(self):
        """Причина жителя и причина менеджера не должны сливаться в одну."""
        text = format_request_details(
            _request(return_reason="Не убрали мусор",
                     manager_return_reason="Переделать шов"),
            language="ru")

        assert "Не убрали мусор" in text
        assert "Переделать шов" in text
        applicant_pos = text.index("Не убрали мусор")
        manager_pos = text.index("Переделать шов")
        assert applicant_pos != manager_pos
        # Между ними обязана быть подпись — иначе читается как один текст.
        between = text[min(applicant_pos, manager_pos):max(applicant_pos, manager_pos)]
        assert between.strip("Не убрали мусорПеределать шов \n"), "нужны разные подписи"

    def test_uz_locale_renders(self):
        text = format_request_details(
            _request(manager_return_reason="Qayta bajarish"), language="uz")

        assert "Qayta bajarish" in text


class TestNotificationKeys:
    def test_manager_and_applicant_returns_use_different_keys(self):
        """Один ключ на два разных события не позволял вставить причину."""
        from uk_management_bot.services.workflow_notifications import _NOTIFY_MATRIX
        from uk_management_bot.utils.request_workflow import Action

        manager_key = _NOTIFY_MATRIX[Action.MANAGER_RETURN_TO_WORK][1]
        applicant_key = _NOTIFY_MATRIX[Action.APPLICANT_RETURN][1]

        assert manager_key != applicant_key

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_manager_return_template_carries_reason(self, language):
        from uk_management_bot.services.workflow_notifications import _NOTIFY_MATRIX
        from uk_management_bot.utils.helpers import get_text
        from uk_management_bot.utils.request_workflow import Action

        key = _NOTIFY_MATRIX[Action.MANAGER_RETURN_TO_WORK][1]
        template = get_text(key, language=language)

        assert "{reason}" in template, "уведомление обязано нести причину"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_applicant_return_template_has_no_reason_placeholder(self, language):
        """У возврата жителем причина берётся из другого поля — плейсхолдер
        менеджерской причины там неуместен и уронил бы format()."""
        from uk_management_bot.services.workflow_notifications import _NOTIFY_MATRIX
        from uk_management_bot.utils.helpers import get_text
        from uk_management_bot.utils.request_workflow import Action

        key = _NOTIFY_MATRIX[Action.APPLICANT_RETURN][1]
        template = get_text(key, language=language)

        assert "{reason}" not in template
