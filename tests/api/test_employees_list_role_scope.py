"""Скоуп основного списка сотрудников (`list_employees`) по роли.

Контекст: список executor-scoped по умолчанию — им кормятся дропдауны назначения
на смену/заявку (там допустимы только исполнители). Явный `role` ДОЛЖЕН ЗАМЕНЯТЬ
этот scope, а не добавляться поверх executor: иначе `role='manager'` давал бы
«executor И manager» → чистые менеджеры (invite-only, без роли executor) никогда
бы не находились на странице «Сотрудники». Здесь фиксируем оба конца:
- default (role=None) → только исполнители (дропдауны целы);
- role='manager' → чистые менеджеры видны.
"""
import pytest

from uk_management_bot.database.models.user import User
from uk_management_bot.api.shifts import service


async def _user(db, tg, *, roles, status="approved", verification="verified"):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="U", last_name=str(tg),
             roles=roles, active_role="executor", status=status,
             verification_status=verification)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _ids(db, **kw):
    kw.setdefault("specialization", None)
    kw.setdefault("has_active_shift", None)
    kw.setdefault("search", None)
    kw.setdefault("role", None)
    kw.setdefault("verification_status", None)
    kw.setdefault("limit", 50)
    kw.setdefault("offset", 0)
    users, _ = await service.list_employees(db, **kw)
    return {u.telegram_id for u in users}


@pytest.mark.asyncio
async def test_default_scope_is_executor_only(db_session):
    """Без role — только исполнители (защита shift-дропдаунов от менеджеров)."""
    await _user(db_session, 3001, roles='["applicant", "executor"]')
    await _user(db_session, 3002, roles='["applicant", "manager"]')     # чистый менеджер
    await _user(db_session, 3003, roles='["applicant", "executor", "manager"]')

    ids = await _ids(db_session)
    assert ids == {3001, 3003}  # 3002 (чистый менеджер) НЕ в дефолтном списке


@pytest.mark.asyncio
async def test_role_manager_returns_pure_managers(db_session):
    """role='manager' ЗАМЕНЯЕТ scope — чистые менеджеры находятся (регресс-кейс)."""
    await _user(db_session, 3101, roles='["applicant", "executor"]')     # чистый исполнитель
    await _user(db_session, 3102, roles='["applicant", "manager"]')      # чистый менеджер
    await _user(db_session, 3103, roles='["applicant", "executor", "manager"]')

    ids = await _ids(db_session, role="manager")
    assert ids == {3102, 3103}  # 3101 (чистый исполнитель) отфильтрован


@pytest.mark.asyncio
async def test_role_manager_excludes_soft_deleted(db_session):
    import datetime
    m = await _user(db_session, 3201, roles='["applicant", "manager"]')
    m.deleted_at = datetime.datetime(2026, 7, 8)
    await db_session.commit()

    ids = await _ids(db_session, role="manager")
    assert 3201 not in ids
