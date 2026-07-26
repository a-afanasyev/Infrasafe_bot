"""AUD5-APIFE-3 — канбан: активная работа не должна вытесняться историей.

Было: один запрос `ORDER BY created_at DESC LIMIT 500` на всю доску. Статусы
«Принято» и «Отменена» копятся вечно, поэтому по достижении 500 строк с доски
пропадали САМЫЕ СТАРЫЕ АКТИВНЫЕ карточки — то есть именно та работа, которую
менеджер обязан видеть, — а `count` в колонке считался по обрезанному набору и
показывал неправду.

Решение владельца (2026-07-27): активные статусы отдаются целиком, терминальные
— верхушкой по колонке, но `count` у них равен НАСТОЯЩЕМУ числу заявок.
Опираться можно на то, что `normalize_status` терминальные статусы не создаёт из
нетерминальных и не меняет их обратно (см. `utils/request_workflow.py`), поэтому
SQL-предикат по `Request.status` совпадает с канон-разбиением точно и логику
нормализации дублировать не требуется.
"""
import pytest

from uk_management_bot.api.requests import router as requests_router
from uk_management_bot.database.models.request import Request as RequestModel


async def _seed(db_session, rn: str, user_id: int, status: str, *, category="Сантехника"):
    db_session.add(RequestModel(
        request_number=rn,
        user_id=user_id,
        category=category,
        description=f"request {rn}",
        status=status,
        source="web",
        media_files=[],
    ))


async def _seed_many(db_session, user_id, *, active: int, terminal: int, terminal_status="Принято"):
    """Терминальные создаются ПОСЛЕ активных: они «свежее» по created_at.

    Порядок важен: старый код брал 500 самых свежих на всю доску, и вытеснялись
    именно старые активные. Тест обязан воспроизводить эту геометрию.
    """
    for i in range(active):
        await _seed(db_session, f"260701-{i:03d}", user_id, "Новая")
    for i in range(terminal):
        await _seed(db_session, f"260702-{i:03d}", user_id, terminal_status)
    await db_session.commit()


def _col(payload, status):
    return next(c for c in payload["columns"] if c["status"] == status)


@pytest.fixture
def small_terminal_limit(monkeypatch):
    """Лимит терминальной колонки → 3, чтобы не сеять сотни строк."""
    monkeypatch.setattr(requests_router, "TERMINAL_COLUMN_LIMIT", 3)


@pytest.mark.asyncio
async def test_terminal_column_is_capped_but_count_is_honest(
    client, db_session, manager_user, small_terminal_limit
):
    """Главный тест пункта: показано 3, а в count — все 7."""
    await _seed_many(db_session, manager_user.id, active=2, terminal=7)

    payload = (await client.get("/api/v2/requests/kanban")).json()
    accepted = _col(payload, "Принято")

    assert len(accepted["requests"]) == 3, "терминальная колонка обязана быть ограничена"
    assert accepted["count"] == 7, "count обязан показывать НАСТОЯЩЕЕ число, а не размер выборки"


@pytest.mark.asyncio
async def test_terminal_column_shows_the_most_recent(
    client, db_session, manager_user, small_terminal_limit
):
    """Верхушка — свежие, а не произвольные три."""
    await _seed_many(db_session, manager_user.id, active=0, terminal=5)

    payload = (await client.get("/api/v2/requests/kanban")).json()
    shown = {r["request_number"] for r in _col(payload, "Принято")["requests"]}

    assert shown == {"260702-004", "260702-003", "260702-002"}


@pytest.mark.asyncio
async def test_active_cards_are_never_truncated(
    client, db_session, manager_user, small_terminal_limit
):
    """Активные не вытесняются историей, сколько бы её ни накопилось."""
    await _seed_many(db_session, manager_user.id, active=5, terminal=9)

    payload = (await client.get("/api/v2/requests/kanban")).json()
    new_col = _col(payload, "Новая")

    assert len(new_col["requests"]) == 5
    assert new_col["count"] == 5
    assert {r["request_number"] for r in new_col["requests"]} == {
        f"260701-{i:03d}" for i in range(5)
    }


@pytest.mark.asyncio
async def test_each_terminal_column_gets_its_own_budget(
    client, db_session, manager_user, small_terminal_limit
):
    """«Отменена» не должна голодать из-за большого числа «Принято».

    Общий лимит на обе терминальные колонки давал бы именно это: сортировка по
    дате отдала бы весь бюджет одному статусу.
    """
    await _seed_many(db_session, manager_user.id, active=0, terminal=6)
    for i in range(4):
        await _seed(db_session, f"260703-{i:03d}", manager_user.id, "Отменена")
    await db_session.commit()

    payload = (await client.get("/api/v2/requests/kanban")).json()

    assert len(_col(payload, "Принято")["requests"]) == 3
    assert _col(payload, "Принято")["count"] == 6
    assert len(_col(payload, "Отменена")["requests"]) == 3
    assert _col(payload, "Отменена")["count"] == 4


@pytest.mark.asyncio
async def test_filters_apply_to_both_partitions(
    client, db_session, manager_user, small_terminal_limit
):
    """Фильтр обязан сужать и активную часть, и терминальную вместе с её count."""
    await _seed(db_session, "260704-001", manager_user.id, "Новая", category="Сантехника")
    await _seed(db_session, "260704-002", manager_user.id, "Новая", category="Электрика")
    for i in range(5):
        await _seed(db_session, f"260705-{i:03d}", manager_user.id, "Принято",
                    category="Сантехника")
    for i in range(2):
        await _seed(db_session, f"260706-{i:03d}", manager_user.id, "Принято",
                    category="Электрика")
    await db_session.commit()

    payload = (await client.get("/api/v2/requests/kanban?category=Электрика")).json()

    assert {r["request_number"] for r in _col(payload, "Новая")["requests"]} == {"260704-002"}
    accepted = _col(payload, "Принято")
    assert accepted["count"] == 2, "count терминальной колонки обязан учитывать фильтр"
    assert {r["request_number"] for r in accepted["requests"]} == {"260706-000", "260706-001"}


@pytest.mark.asyncio
async def test_empty_board_reports_zero_everywhere(client, db_session, manager_user):
    """Пустая доска: все колонки на месте, count=0 — а не отсутствующие колонки."""
    payload = (await client.get("/api/v2/requests/kanban")).json()

    assert [c["status"] for c in payload["columns"]] == requests_router.KANBAN_STATUSES
    assert all(c["count"] == 0 and c["requests"] == [] for c in payload["columns"])
