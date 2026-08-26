"""Фильтр списка сотрудников под требования ШАБЛОНА СМЕНЫ (`for_specializations`).

Контекст: модалка «Создать смену из шаблона» показывала ВСЕХ исполнителей —
менеджер выбирал сантехника в смену «Благоустройство + Уборка». Фильтр живёт
на сервере и повторяет семантику guard'а шаблонов
(`has_required_template_specs` → `matches_raw_requirement`):
- требование — CSV канон-токенов из `required_specializations` шаблона;
- `universal` в требовании = «подойдёт кто угодно»;
- `universal` у исполнителя = «умеет всё»;
- достаточно ОДНОГО совпадения;
- нерезолвимое требование fail-closed — не пропускает никого (опечатка в
  шаблоне не должна молча превращаться в «без ограничений»).

Отличие от `for_category` (одна специализация из категории ЗАЯВКИ): здесь
требование — набор специализаций шаблона, как есть.
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
    return u


async def _ids(db, **kw):
    kw.setdefault("specialization", None)
    kw.setdefault("has_active_shift", None)
    kw.setdefault("search", None)
    kw.setdefault("role", None)
    kw.setdefault("verification_status", None)
    kw.setdefault("for_category", None)
    kw.setdefault("for_specializations", None)
    kw.setdefault("limit", 50)
    kw.setdefault("offset", 0)
    users, _ = await service.list_employees(db, **kw)
    return {u.telegram_id for u in users}


@pytest.mark.asyncio
async def test_single_requirement_keeps_matching_only(db_session):
    await _executor(db_session, 5001, specialization="landscaping")
    await _executor(db_session, 5002, specialization="plumber")

    ids = await _ids(db_session, for_specializations="landscaping")
    assert ids == {5001}


@pytest.mark.asyncio
async def test_multi_requirement_one_match_is_enough(db_session):
    """Фокус шаблона — «что смена покрывает»: уборщик подходит смене
    «благоустройство + уборка», владеть обеими не обязан."""
    await _executor(db_session, 5101, specialization="cleaning")
    await _executor(db_session, 5102, specialization="electrician")

    ids = await _ids(db_session, for_specializations="landscaping,cleaning")
    assert ids == {5101}


@pytest.mark.asyncio
async def test_universal_executor_matches_any_template(db_session):
    await _executor(db_session, 5201, specialization="universal")
    await _executor(db_session, 5202, specialization="plumber")

    ids = await _ids(db_session, for_specializations="landscaping")
    assert ids == {5201}


@pytest.mark.asyncio
async def test_universal_requirement_matches_everyone(db_session):
    await _executor(db_session, 5301, specialization="plumber")
    await _executor(db_session, 5302, specialization=None)

    ids = await _ids(db_session, for_specializations="universal")
    assert ids == {5301, 5302}


@pytest.mark.asyncio
async def test_unresolvable_requirement_is_fail_closed(db_session):
    """Опечатка в требовании не превращается в «без ограничений»."""
    await _executor(db_session, 5401, specialization="plumber")
    await _executor(db_session, 5402, specialization="universal")

    ids = await _ids(db_session, for_specializations="опечатка-такой-нет")
    assert ids == set()


@pytest.mark.asyncio
async def test_no_param_keeps_everyone(db_session):
    await _executor(db_session, 5501, specialization="plumber")
    await _executor(db_session, 5502, specialization=None)

    ids = await _ids(db_session)
    assert ids == {5501, 5502}
