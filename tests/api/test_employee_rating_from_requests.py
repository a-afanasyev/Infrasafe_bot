"""«Рейтинг» на карточке сотрудника = средний балл заявок исполнителя.

Раньше поле считалось как avg(Shift.quality_rating) — колонку не пишет ни один
прод-код, карточка всегда показывала «—». Теперь источник — реальные оценки
жителей (1–5) при приёмке: AVG(ratings.rating) по заявкам, где сотрудник —
исполнитель (requests.executor_id; переживает легаси-заявки без строк
RequestAssignment).
"""
import pytest

from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.user import User
from uk_management_bot.api.shifts import service


async def _executor(db, tg):
    u = User(telegram_id=tg, username=f"e{tg}", first_name="E", last_name=str(tg),
             roles='["executor"]', status="approved")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _rated_request(db, number, *, owner_id, executor_id, rating):
    db.add(RequestModel(request_number=number, user_id=owner_id,
                        category="Сантехника", description="d",
                        status="Принято", executor_id=executor_id))
    db.add(Rating(request_number=number, user_id=owner_id, rating=rating))
    await db.commit()


@pytest.mark.asyncio
async def test_rating_is_mean_of_executor_request_stars(db_session, manager_user):
    executor = await _executor(db_session, tg=3001)
    await _rated_request(db_session, "260820-001", owner_id=manager_user.id,
                         executor_id=executor.id, rating=5)
    await _rated_request(db_session, "260820-002", owner_id=manager_user.id,
                         executor_id=executor.id, rating=2)

    row = await service.get_employee_with_stats(db_session, executor.id)

    assert row is not None
    *_, rating = row
    assert rating == pytest.approx(3.5)


@pytest.mark.asyncio
async def test_rating_ignores_other_executors_requests(db_session, manager_user):
    executor = await _executor(db_session, tg=3002)
    other = await _executor(db_session, tg=3003)
    await _rated_request(db_session, "260820-003", owner_id=manager_user.id,
                         executor_id=executor.id, rating=4)
    await _rated_request(db_session, "260820-004", owner_id=manager_user.id,
                         executor_id=other.id, rating=1)

    row = await service.get_employee_with_stats(db_session, executor.id)

    *_, rating = row
    assert rating == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_rating_is_none_without_rated_requests(db_session):
    executor = await _executor(db_session, tg=3004)

    row = await service.get_employee_with_stats(db_session, executor.id)

    *_, rating = row
    assert rating is None
