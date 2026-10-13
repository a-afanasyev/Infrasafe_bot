"""Ad-hoc смена (старт из бота) не несёт specialization_focus → дашборд
клал исполнителя в «Универсалы», хотя в «Сотрудниках» он сантехник.
Брифу нужен тот же фоллбэк на спец-цию исполнителя, что у бота (FS-10).
Legacy-токен профиля (`plumbing`) отдаётся каноном (`plumber`) — как у шаблонов."""
from datetime import datetime

from uk_management_bot.api.shifts.router._helpers import _shift_brief
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User


def _shift(focus):
    return Shift(id=1, user_id=7, status="active", start_time=datetime(2026, 10, 13, 8),
                 max_requests=10, current_request_count=0, specialization_focus=focus)


def test_empty_focus_falls_back_to_executor_specialization():
    user = User(id=7, telegram_id=1, specialization='["plumbing"]')
    assert _shift_brief(_shift(None), user).specialization_focus == ["plumber"]
    assert _shift_brief(_shift([]), user).specialization_focus == ["plumber"]


def test_explicit_focus_wins():
    user = User(id=7, telegram_id=1, specialization='["plumbing"]')
    assert _shift_brief(_shift(["electric"]), user).specialization_focus == ["electric"]


def test_universal_or_missing_executor_stays_unspecified():
    universal = User(id=7, telegram_id=1, specialization='["universal"]')
    assert not _shift_brief(_shift(None), universal).specialization_focus
    assert not _shift_brief(_shift(None), None).specialization_focus
