"""BUG-128 — `POST /api/v2/shifts` не заполнял `planned_*`, и смена из дашборда
была невидима исполнителю.

Три пути создают/меняют смену, и до 2026-07-26 только один из них не
синхронизировал плановые времена:

* `create_shifts_from_template` — ставит `planned_* = start/end` (комментарий там
  прямо говорит: бот-расписание читает `planned_*`, иначе показывает «??:??»);
* `apply_shift_update` (PATCH) — синхронизирует при смене `start_time`/`end_time`;
* `create_shift` (POST) — **не ставил вообще**.

Симптом: менеджер создаёт смену в веб-дашборде → `planned_start_time` остаётся
`NULL` → `handlers/my_shifts.py:handle_week_schedule` фильтрует по
`func.date(Shift.planned_start_time)` и такую смену исполнителю не показывает.
Исполнитель видел только смены бот-планировщика и from-template.

Тесты идут через сервисный слой, а не HTTP-ответ: sqlite (тестовый движок) не
хранит tzinfo на `DateTime(timezone=True)`, поэтому сравнивать надо сами
значения полей после `refresh`, а офсет в JSON тут ничего не доказывает (та же
причина зафиксирована в `test_shift_overlap.py`).
"""
from datetime import datetime, timezone, timedelta

import pytest

from uk_management_bot.api.shifts import service
from uk_management_bot.database.models.user import User

START = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=8)


class _Body:
    """Минимальный стенд вместо `CreateShiftBody`: тест про синхронизацию полей,
    а не про валидацию схемы (её держит `test_shift_schemas.py`)."""

    def __init__(self, user_id, start_time=START, end_time=END):
        self.user_id = user_id
        self.start_time = start_time
        self.end_time = end_time
        self.shift_type = "regular"
        self.specialization_focus = []
        self.max_requests = 10
        self.priority_level = 1
        self.notes = None


async def _executor(db, tg=91280):
    u = User(telegram_id=tg, username="ex", first_name="Ex",
             roles='["executor"]', active_role="executor", status="approved")
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_create_shift_mirrors_planned_times(db_session):
    """Ровно тот дефект: без плановых времён смена не видна в расписании."""
    user = await _executor(db_session)
    await db_session.commit()

    shift = await service.create_shift(db_session, body=_Body(user.id))

    assert shift.planned_start_time is not None, (
        "planned_start_time остался NULL — исполнитель не увидит смену в "
        "«Мои смены → Расписание на неделю» (фильтр по planned_start_time)"
    )
    assert shift.planned_end_time is not None
    assert shift.planned_start_time == shift.start_time
    assert shift.planned_end_time == shift.end_time


@pytest.mark.asyncio
async def test_all_three_paths_agree_on_planned_times(db_session):
    """Контракт, а не отдельная правка: POST и PATCH дают одно и то же.

    Именно расхождение путей и было дефектом, поэтому проверяется согласие, а не
    поведение одного из них по отдельности.
    """
    user = await _executor(db_session, tg=91281)
    await db_session.commit()

    created = await service.create_shift(db_session, body=_Body(user.id))
    assert (created.planned_start_time, created.planned_end_time) == (
        created.start_time, created.end_time
    )

    new_start = START + timedelta(days=1)
    new_end = END + timedelta(days=1)
    updated = await service.apply_shift_update(
        db_session, shift=created,
        data={"start_time": new_start, "end_time": new_end},
    )
    assert (updated.planned_start_time, updated.planned_end_time) == (
        updated.start_time, updated.end_time
    ), "PATCH и POST разошлись в трактовке planned_* — вернулся класс BUG-128"


@pytest.mark.asyncio
async def test_open_ended_shift_keeps_planned_end_none(db_session):
    """Смена без `end_time` (open-ended) не должна получить выдуманный конец.

    Граница: зеркалирование обязано копировать значение, а не подставлять что-то
    вместо `None`, иначе бот-расписание нарисует несуществующее окончание.
    """
    user = await _executor(db_session, tg=91282)
    await db_session.commit()

    shift = await service.create_shift(
        db_session, body=_Body(user.id, end_time=None)
    )

    assert shift.planned_start_time == shift.start_time
    assert shift.planned_end_time is None
