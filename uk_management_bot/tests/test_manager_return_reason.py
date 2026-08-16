"""Причина возврата менеджером терялась: исполнитель не знал, что переделывать.

`MANAGER_RETURN_TO_WORK` принимал `reason` опционально, планировщик патчей его
игнорировал, а бот-кнопка слала пустой payload — текст оседал только в
`audit_logs`, куда исполнитель не смотрит. Заявка возвращалась «молча».

Теперь причина обязательна и непуста (решение владельца), пишется в отдельную
колонку `requests.manager_return_reason` и видна исполнителю и жителю.

Отдельная колонка, а не `notes`: notes затирается обычным менеджерским PATCH
(`_MANAGER_EDIT_FIELDS`) и уже занят уточнением/отменой. Существующий
`return_reason` (причина ЖИТЕЛЯ) не трогаем — это контекст, на который менеджер
и отвечает; в карточке они различаются подписями.
"""

from datetime import datetime, timezone

import pytest

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_IN_PROGRESS,
)
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    ActorContext,
    Op,
    PayloadInvalid,
    PrincipalRef,
    RequestState,
    WorkflowSnapshot,
    plan_transition,
)

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
OWNER_ID, EXECUTOR_ID, MANAGER_ID = 1, 4, 5

MANAGER = ActorContext(
    kind="user", user_id=MANAGER_ID, system_actor=None,
    roles=frozenset({"manager"}), active_role="manager",
)


def _snap(status=REQUEST_STATUS_COMPLETED, *, returned=False):
    return WorkflowSnapshot(
        request=RequestState(
            request_number="260817-001", status=status, user_id=OWNER_ID,
            executor_id=EXECUTOR_ID, is_returned=returned,
            manager_confirmed=False,
        ),
    )


def _plan(payload):
    return plan_transition(
        _snap(returned=True),
        ActionCommand("cmd-1", Action.MANAGER_RETURN_TO_WORK, payload),
        MANAGER,
        PrincipalRef(kind="user", user_id=MANAGER_ID, source="telegram"),
        NOW,
    )


class TestReasonRequired:
    def test_missing_reason_rejected(self):
        """Пустой payload больше не проходит — раньше именно его слал бот."""
        with pytest.raises(PayloadInvalid):
            _plan({})

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_blank_reason_rejected(self, blank):
        """Проверки типа мало: пробелы — формально str, но исполнителю пусто."""
        with pytest.raises(PayloadInvalid):
            _plan({"reason": blank})

    def test_non_string_reason_rejected(self):
        with pytest.raises(PayloadInvalid):
            _plan({"reason": 42})


class TestReasonPersisted:
    def test_reason_lands_in_patch(self):
        res = _plan({"reason": "Плитка положена криво, переделать"})

        patch = {field: value for field, op, value in res.patch if op == Op.SET}
        assert patch["manager_return_reason"] == "Плитка положена криво, переделать"

    def test_reason_is_trimmed(self):
        """Хвостовые пробелы из Telegram-ввода не должны попадать в карточку."""
        res = _plan({"reason": "  Переделать шов  "})

        patch = {field: value for field, op, value in res.patch if op == Op.SET}
        assert patch["manager_return_reason"] == "Переделать шов"

    def test_existing_flags_still_reset(self):
        """Прежнее поведение перехода сохраняется — причина его не подменяет."""
        res = _plan({"reason": "переделать"})

        patch = {field: value for field, op, value in res.patch if op == Op.SET}
        assert patch["is_returned"] is False
        assert patch["manager_confirmed"] is False
        assert res.new_canon_status == REQUEST_STATUS_IN_PROGRESS

    def test_applicant_return_reason_untouched(self):
        """Причину ЖИТЕЛЯ переход менеджера не перезаписывает."""
        res = _plan({"reason": "переделать"})

        touched = {field for field, _op, _v in res.patch}
        assert "return_reason" not in touched
