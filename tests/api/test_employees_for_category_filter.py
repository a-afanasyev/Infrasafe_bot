"""Фильтр списка сотрудников под категорию заявки (`for_category`).

Контекст: дропдауны назначения/переназначения исполнителя на дашборде
(`ExecutorPicker`) кормятся `list_employees` и показывали ВСЕХ verified-
исполнителей, тогда как бот в тех же флоу давно фильтрует по специализации
категории. Фильтр живёт на сервере и решается ЕДИНСТВЕННЫМ предикатом проекта
`matches_required_specs` (урок BUG-166: девять локальных копий семантики
противоречили друг другу) — фронт передаёт только категорию заявки.

Ключевые грани семантики:
- категория → специализация через `get_specialization_for_category`
  (неизвестная категория = `repair`, разнорабочий);
- `universal` у исполнителя = «умеет всё» → виден в любой категории;
- исполнитель без специализации не подходит ни под одну категорию;
- хранение спецификаций разнородно (JSON-список/CSV/скаляр) — парсит канон.
"""
import pytest

from uk_management_bot.api.shifts import service
from uk_management_bot.database.models.user import User


async def _executor(db, tg, *, specialization):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="U", last_name=str(tg),
             roles='["applicant", "executor"]', active_role="executor",
             status="approved", verification_status="verified",
             specialization=specialization)
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
    kw.setdefault("for_category", None)
    kw.setdefault("limit", 50)
    kw.setdefault("offset", 0)
    users, _ = await service.list_employees(db, **kw)
    return {u.telegram_id for u in users}


@pytest.mark.asyncio
async def test_for_category_keeps_only_matching_specialization(db_session):
    await _executor(db_session, 4001, specialization="electrician")
    await _executor(db_session, 4002, specialization="plumber")

    ids = await _ids(db_session, for_category="electricity")
    assert ids == {4001}


@pytest.mark.asyncio
async def test_universal_executor_matches_any_category(db_session):
    await _executor(db_session, 4101, specialization="universal")
    await _executor(db_session, 4102, specialization="plumber")

    ids = await _ids(db_session, for_category="electricity")
    assert ids == {4101}


@pytest.mark.asyncio
async def test_unknown_category_falls_back_to_repair(db_session):
    """Неизвестная категория = разнорабочий (`repair`), а не «все подряд»."""
    await _executor(db_session, 4201, specialization="repair")
    await _executor(db_session, 4202, specialization="plumber")

    ids = await _ids(db_session, for_category="что-то небывалое")
    assert ids == {4201}


@pytest.mark.asyncio
async def test_executor_without_specialization_filtered_out(db_session):
    await _executor(db_session, 4301, specialization=None)
    await _executor(db_session, 4302, specialization="electrician")

    ids = await _ids(db_session, for_category="electricity")
    assert ids == {4302}


@pytest.mark.asyncio
async def test_json_list_storage_is_parsed(db_session):
    """Хранение JSON-списком — легитимный формат, парсит канон-парсер."""
    await _executor(db_session, 4401, specialization='["plumber", "electrician"]')
    await _executor(db_session, 4402, specialization='["plumber"]')

    ids = await _ids(db_session, for_category="electricity")
    assert ids == {4401}


@pytest.mark.asyncio
async def test_no_for_category_keeps_everyone(db_session):
    """Без параметра поведение прежнее — фильтра нет (регресс-кейс)."""
    await _executor(db_session, 4501, specialization="electrician")
    await _executor(db_session, 4502, specialization="plumber")
    await _executor(db_session, 4503, specialization=None)

    ids = await _ids(db_session)
    assert ids == {4501, 4502, 4503}


@pytest.mark.asyncio
async def test_for_category_composes_with_verification_status(db_session):
    """Пикер шлёт оба фильтра разом — verified-гейт не должен теряться."""
    await _executor(db_session, 4601, specialization="electrician")
    unverified = await _executor(db_session, 4602, specialization="electrician")
    unverified.verification_status = "pending"
    await db_session.commit()

    ids = await _ids(db_session, for_category="electricity",
                     verification_status="verified")
    assert ids == {4601}
