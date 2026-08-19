"""Тесты services/auto_manager/rule_engine.py: select_executor.

Паттерн sqlite-фикстуры — как в test_auto_manager_window.py/
test_shift_transfer_rebuild.py (create_engine "sqlite:///:memory:" +
Base.metadata.create_all); билдеры User/Shift/Request — как в
test_shift_transfer_rebuild.py.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.auto_manager.rule_engine import select_executor
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
)

SPECIALIZATION = "plumber"
OTHER_SPECIALIZATION = "electric"

NOW = datetime(2026, 7, 23, 2, 0, tzinfo=timezone.utc)  # overnight, inside a shift
APPLICANT_ID = 999  # заявитель-заглушка для Request.user_id (FK), не тест-предмет


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    # Заявитель-заглушка: Request.user_id — NOT NULL FK на users.id.
    session.add(User(id=APPLICANT_ID, telegram_id=APPLICANT_ID, roles='["applicant"]', status="approved"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _executor(db, uid, tg, *, roles='["executor"]', status="approved", specialization=SPECIALIZATION):
    u = User(
        id=uid,
        telegram_id=tg,
        roles=roles,
        active_role="executor",
        status=status,
        specialization=specialization,
    )
    db.add(u)
    db.commit()
    return u


def _shift(db, sid, user_id, *, status="active", specs=None, start=None, end=None):
    s = Shift(
        id=sid,
        user_id=user_id,
        status=status,
        start_time=start if start is not None else NOW - timedelta(hours=1),
        end_time=end if end is not None else NOW + timedelta(hours=6),
        specialization_focus=specs,
    )
    db.add(s)
    db.commit()
    return s


def _request(db, number, executor_id, *, status=REQUEST_STATUS_IN_PROGRESS):
    r = Request(
        request_number=number,
        user_id=APPLICANT_ID,
        category="plumbing",
        description="desc",
        status=status,
        executor_id=executor_id,
    )
    db.add(r)
    db.commit()
    return r


# ─────────────────────────── no candidates ───────────────────────────


def test_no_candidates_wrong_specialization_returns_none(db):
    ex = _executor(db, 1, 1001, specialization=OTHER_SPECIALIZATION)
    _shift(db, 1, ex.id)

    assert select_executor(db, SPECIALIZATION, NOW) is None


def test_no_users_at_all_returns_none(db):
    assert select_executor(db, SPECIALIZATION, NOW) is None


# ─────────────────────────── shift eligibility ───────────────────────────


def test_candidate_without_active_shift_excluded(db):
    _executor(db, 1, 1001)
    # Нет ни одной смены вовсе.

    assert select_executor(db, SPECIALIZATION, NOW) is None


def test_candidate_with_expired_shift_excluded(db):
    ex = _executor(db, 1, 1001)
    # Смена закончилась до `now`.
    _shift(
        db, 1, ex.id,
        start=NOW - timedelta(hours=10),
        end=NOW - timedelta(hours=2),
    )

    assert select_executor(db, SPECIALIZATION, NOW) is None


def test_candidate_shift_focus_excludes_specialization(db):
    ex = _executor(db, 1, 1001)
    # Активная смена, но фокус — другая специализация (не universal).
    _shift(db, 1, ex.id, specs=[OTHER_SPECIALIZATION])

    assert select_executor(db, SPECIALIZATION, NOW) is None


def test_candidate_with_two_overlapping_active_shifts_matching_one_found(db):
    # Регрессия: проект допускает перекрывающиеся активные смены разных
    # специализаций (напр. electric + plumber одновременно). Раньше
    # select_executor брал ОДНУ произвольную активную смену через
    # AdminHandlerService.get_active_shift_for's .first() и проверял фокус
    # только на ней — если .first() возвращал electric-смену, plumber-запрос
    # ложно давал None, даже когда подходящая plumber-смена тоже активна.
    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id, specs=[OTHER_SPECIALIZATION])  # electric — не подходит
    _shift(db, 2, ex.id, specs=[SPECIALIZATION])  # plumber — подходит

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == ex.id


def test_candidate_shift_focus_includes_specialization_included(db):
    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id, specs=[SPECIALIZATION, OTHER_SPECIALIZATION])

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == ex.id


def test_candidate_shift_focus_universal_token_included(db):
    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id, specs=["universal"])

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == ex.id


def test_candidate_universal_shift_none_focus_included(db):
    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id, specs=None)

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == ex.id


# ─────────────────────────── ranking: least-loaded ───────────────────────────


def test_multiple_candidates_lowest_load_wins(db):
    busy = _executor(db, 1, 1001)
    idle = _executor(db, 2, 1002)
    _shift(db, 1, busy.id)
    _shift(db, 2, idle.id)

    _request(db, "260723-001", busy.id, status=REQUEST_STATUS_IN_PROGRESS)
    _request(db, "260723-002", busy.id, status=REQUEST_STATUS_PURCHASE)
    _request(db, "260723-003", idle.id, status=REQUEST_STATUS_IN_PROGRESS)

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == idle.id


def test_equal_load_tie_break_by_lowest_executor_id(db):
    # Оба кандидата с равной (нулевой) нагрузкой — детерминированный тай-брейк
    # по наименьшему executor_id, не по порядку вставки/итерации.
    first = _executor(db, 5, 1005)
    second = _executor(db, 3, 1003)
    _shift(db, 1, first.id)
    _shift(db, 2, second.id)

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == min(first.id, second.id) == 3


def test_equal_load_tie_break_survives_reversed_candidate_order(db, monkeypatch):
    # SQLite (без ORDER BY) уже отдаёт строки по возрастанию id, поэтому тест
    # выше проходит, даже если явный `user.id`-тай-брейк убрать (порядок
    # кандидатов на входе случайно совпадает с ожидаемым результатом). Здесь
    # список кандидатов принудительно переворачивается (id 3 идёт ПОСЛЕ id 5),
    # чтобы победа id=3 доказывала работу самого тай-брейка `(load, user.id)`,
    # а не побочный эффект порядка строк в БД. На проде (Postgres) порядок
    # незапрошенного SELECT вообще не гарантирован — тай-брейк обязателен.
    first = _executor(db, 5, 1005)
    second = _executor(db, 3, 1003)
    _shift(db, 1, first.id)
    _shift(db, 2, second.id)

    from uk_management_bot.services.admin_handler_service import AdminHandlerService

    original = AdminHandlerService.list_approved_users

    def reversed_order(self):
        return list(reversed(original(self)))

    monkeypatch.setattr(AdminHandlerService, "list_approved_users", reversed_order)

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == 3


def test_load_count_ignores_statuses_outside_the_three(db):
    # candidate A: много заявок в статусе "Исполнено" (COMPLETED) — НЕ входит
    # в OPEN_LOAD_STATUSES, поэтому не должно повышать его "нагрузку".
    # candidate B: одна заявка в "В работе" — реально открыта.
    a = _executor(db, 1, 1001)
    b = _executor(db, 2, 1002)
    _shift(db, 1, a.id)
    _shift(db, 2, b.id)

    for i in range(5):
        _request(db, f"260723-{i:03d}", a.id, status=REQUEST_STATUS_COMPLETED)
    _request(db, "260723-900", b.id, status=REQUEST_STATUS_IN_PROGRESS)

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == a.id  # a's effective load is 0 < b's load of 1


def test_load_counts_all_three_open_statuses(db):
    a = _executor(db, 1, 1001)
    b = _executor(db, 2, 1002)
    _shift(db, 1, a.id)
    _shift(db, 2, b.id)

    _request(db, "260723-001", a.id, status=REQUEST_STATUS_IN_PROGRESS)
    _request(db, "260723-002", a.id, status=REQUEST_STATUS_PURCHASE)
    _request(db, "260723-003", a.id, status=REQUEST_STATUS_CLARIFICATION)
    # b has none → b should win despite a having only 3 requests total.

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == b.id


# ─────────────────────────── candidate filter mirrors reference ───────────────────────────


def test_non_approved_executor_excluded(db):
    ex = _executor(db, 1, 1001, status="pending")
    _shift(db, 1, ex.id)

    assert select_executor(db, SPECIALIZATION, NOW) is None


def test_approved_non_executor_role_excluded(db):
    ex = _executor(db, 1, 1001, roles='["applicant"]')
    _shift(db, 1, ex.id)

    assert select_executor(db, SPECIALIZATION, NOW) is None


def test_csv_roles_format_still_recognized_as_executor(db):
    # get_user_roles/parse_roles_safe понимает и CSV-формат, не только JSON-список
    # (в отличие от list_approved_executors' SQL LIKE '"executor"').
    ex = _executor(db, 1, 1001, roles="applicant,executor")
    _shift(db, 1, ex.id)

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == ex.id


def test_select_executor_with_snapshot_does_zero_queries(db):
    """AUD6-P2-14: со срезом дежурства выбор исполнителя не ходит в БД вовсе —
    оркестратор строит снапшот один раз на тик и переиспользует на все заявки."""
    from sqlalchemy import event

    from uk_management_bot.services.auto_manager.rule_engine import build_duty_snapshot

    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id)

    snapshot = build_duty_snapshot(db, NOW)

    counter = {"n": 0}

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = select_executor(db, SPECIALIZATION, NOW, snapshot=snapshot)
    finally:
        event.remove(engine, "before_cursor_execute", _before)

    assert result is not None and result.id == ex.id
    assert counter["n"] == 0, f"select_executor со снапшотом сделал {counter['n']} запросов"


def test_snapshot_load_bump_spreads_burst_within_tick(db):
    """Пачка однотипных заявок одного тика не должна уходить одному исполнителю:
    оркестратор инкрементирует load_by_user после каждого назначения."""
    from uk_management_bot.services.auto_manager.rule_engine import build_duty_snapshot

    first = _executor(db, 1, 1001)
    second = _executor(db, 2, 1002)
    _shift(db, 1, first.id)
    _shift(db, 2, second.id)

    snapshot = build_duty_snapshot(db, NOW)

    pick1 = select_executor(db, SPECIALIZATION, NOW, snapshot=snapshot)
    snapshot.load_by_user[pick1.id] = snapshot.load_by_user.get(pick1.id, 0) + 1
    pick2 = select_executor(db, SPECIALIZATION, NOW, snapshot=snapshot)

    assert {pick1.id, pick2.id} == {first.id, second.id}


def test_universal_executor_is_a_candidate(db):
    """BUG-166: `universal` у исполнителя — джокер и на шаге отбора кандидатов.

    Шаг 1 (`specialization in parse_specializations`) джокера не знал, а шаг 2
    (`Shift.can_handle_specialization`) знал — одна функция отвечала на вопрос
    «джокер ли universal» по-разному в зависимости от стороны.
    """
    ex = _executor(db, 1, 1001, specialization='["universal"]')
    _shift(db, 1, ex.id, specs=[SPECIALIZATION])

    result = select_executor(db, SPECIALIZATION, NOW)
    assert result is not None
    assert result.id == ex.id


def test_unrelated_specialization_still_excluded(db):
    """…но джокером не становится любая другая специализация."""
    ex = _executor(db, 1, 1001, specialization='["cleaning"]')
    _shift(db, 1, ex.id, specs=[SPECIALIZATION])

    assert select_executor(db, SPECIALIZATION, NOW) is None


@pytest.mark.parametrize("spec", [None, "", "   ", "[]"])
def test_blank_requirement_selects_nobody(db, spec):
    """Пустое требование НЕ означает «подойдёт любой».

    `requests.assigned_group` — nullable, и на NULL прежнее `specialization in
    parse_specializations(...)` не пропускало никого: заявка эскалировалась
    менеджеру. Перевод на общий предикат легко ломает именно это — предикат
    трактует пустое требование как «ограничений нет».
    """
    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id, specs=[SPECIALIZATION])

    assert select_executor(db, spec, NOW) is None


# ──────────────────── exclude_user_ids (переназначение) ────────────────────
#
# Отсев обязан идти ДО ranking'а: select_executor отдаёт только top-1, и
# отбросить его снаружи значило бы остаться без фолбэка на следующего. Поэтому
# тест проверяет именно ФОЛБЭК на №2, а не просто «первого нет в ответе».


def test_exclude_user_ids_falls_back_to_next_by_load(db):
    idle = _executor(db, 2, 1002)      # выиграл бы по нагрузке
    busier = _executor(db, 7, 1007)
    _shift(db, 1, idle.id)
    _shift(db, 2, busier.id)
    _request(db, "260723-010", busier.id, status=REQUEST_STATUS_IN_PROGRESS)

    assert select_executor(db, SPECIALIZATION, NOW).id == idle.id

    result = select_executor(db, SPECIALIZATION, NOW,
                             exclude_user_ids=frozenset({idle.id}))
    assert result is not None, "исключение победителя не должно обнулять подбор"
    assert result.id == busier.id


def test_exclude_user_ids_all_candidates_returns_none(db):
    only = _executor(db, 4, 1004)
    _shift(db, 1, only.id)

    assert select_executor(db, SPECIALIZATION, NOW,
                           exclude_user_ids=frozenset({only.id})) is None


def test_exclude_user_ids_default_empty_keeps_background_callers_intact(db):
    ex = _executor(db, 6, 1006)
    _shift(db, 1, ex.id)

    assert select_executor(db, SPECIALIZATION, NOW).id == ex.id

