"""
FIX-003 — Покрытие миграции `requests.apartment_id` FK -> ON DELETE SET NULL.

Тест выполняется против реального PostgreSQL (тот же DATABASE_URL, что и у бота),
поскольку поведение `ON DELETE` — это специфика конкретного диалекта/движка БД
и не воспроизводится в SQLite-фикстурах.

AC: удаление apartment с историческими requests не падает на FK violation,
`requests.apartment_id` становится NULL, строка request сохраняется.
"""
from __future__ import annotations

import datetime as _dt
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — postgres-only test, skipping")
    return url


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(_database_url(), future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def seeded_apartment_with_request(session):
    """Создаёт минимальный набор: yard -> building -> apartment -> request.
    Возвращает кортеж (apartment_id, request_number). Все объекты помечены
    уникальным суффиксом, чтобы не конфликтовать с реальными данными."""
    suffix = uuid.uuid4().hex[:8]

    # 1. Yard
    yard_id = session.execute(
        text(
            "INSERT INTO yards (name, is_active, created_at) "
            "VALUES (:name, true, now()) RETURNING id"
        ),
        {"name": f"test-yard-{suffix}"},
    ).scalar_one()

    # 2. Building
    building_id = session.execute(
        text(
            "INSERT INTO buildings (address, yard_id, entrance_count, floor_count, "
            "is_active, created_at) "
            "VALUES (:addr, :yard, 1, 1, true, now()) RETURNING id"
        ),
        {"addr": f"test-bld-{suffix}", "yard": yard_id},
    ).scalar_one()

    # 3. Apartment
    apartment_id = session.execute(
        text(
            "INSERT INTO apartments (building_id, apartment_number, is_active, created_at) "
            "VALUES (:bld, :num, true, now()) RETURNING id"
        ),
        {"bld": building_id, "num": f"T{suffix}"},
    ).scalar_one()

    # 4. User (заявитель)
    # NB: source-of-truth для роли в логике — active_role + roles JSON (CLAUDE.md).
    # Колонка `role` здесь установлена ТОЛЬКО потому, что schema-level NOT NULL
    # без server_default. Серверный default — отдельный шаг (out of scope FIX-003).
    user_id = session.execute(
        text(
            "INSERT INTO users (telegram_id, role, roles, active_role, status, language, "
            "verification_status, created_at) "
            "VALUES (:tg, 'applicant', '[\"applicant\"]', 'applicant', 'approved', 'ru', "
            "'verified', now()) RETURNING id"
        ),
        # уникальный отрицательный telegram_id, чтобы не пересечься с реальными
        {"tg": -int(uuid.uuid4().int % 10**9)},
    ).scalar_one()

    # 5. Request — canonical YYMMDD-NNN format (NNN из верхнего диапазона 900-999,
    # вне типичных production-номеров → меньше шанс коллизии)
    today = _dt.date.today().strftime("%y%m%d")
    request_number = f"{today}-{900 + int(suffix[:2], 16) % 100:03d}"
    session.execute(
        text(
            "INSERT INTO requests (request_number, user_id, category, status, "
            "description, urgency, apartment_id, is_returned, manager_confirmed, "
            "created_at) "
            "VALUES (:rn, :uid, 'test-category', 'Новая', 'test description', "
            "'Обычная', :apt, false, false, now())"
        ),
        {"rn": request_number, "uid": user_id, "apt": apartment_id},
    )
    session.commit()

    yield apartment_id, request_number, building_id, yard_id, user_id

    # Cleanup — порядок важен: requests -> apartments -> buildings -> yards -> users
    session.rollback()
    session.execute(text("DELETE FROM requests WHERE request_number = :rn"), {"rn": request_number})
    session.execute(text("DELETE FROM apartments WHERE id = :id"), {"id": apartment_id})
    session.execute(text("DELETE FROM buildings WHERE id = :id"), {"id": building_id})
    session.execute(text("DELETE FROM yards WHERE id = :id"), {"id": yard_id})
    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    session.commit()


def test_apartment_purge_keeps_request_history(session, seeded_apartment_with_request):
    """
    Удаление apartment с историческими requests:
      1. НЕ падает на FK violation
      2. строка request сохраняется
      3. requests.apartment_id становится NULL
    """
    apartment_id, request_number, *_ = seeded_apartment_with_request

    # Sanity: request действительно ссылается на apartment_id
    pre = session.execute(
        text("SELECT apartment_id FROM requests WHERE request_number = :rn"),
        {"rn": request_number},
    ).scalar_one()
    assert pre == apartment_id, "fixture broken: request не ссылается на apartment"

    # ── act: удаляем apartment
    try:
        session.execute(text("DELETE FROM apartments WHERE id = :id"), {"id": apartment_id})
        session.commit()
    except IntegrityError as exc:
        pytest.fail(
            "FK violation on apartment delete — миграция SET NULL не применена. "
            f"Ошибка: {exc}"
        )

    # ── assert: request остался, apartment_id обнулён
    row = session.execute(
        text(
            "SELECT request_number, apartment_id FROM requests "
            "WHERE request_number = :rn"
        ),
        {"rn": request_number},
    ).first()
    assert row is not None, "request пропал после удаления apartment"
    assert row.apartment_id is None, (
        f"ожидался NULL в requests.apartment_id, получено: {row.apartment_id}"
    )
