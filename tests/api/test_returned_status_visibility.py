"""SSOT-кластер #1 PR7 — раскрытие канон-статуса «Возвращена» приложению.

После cutover (PR3+4) статус «Возвращена» хранится напрямую, но наружу
проецировался в «Исполнено» для ВСЕХ потребителей (включая менеджерский
дашборд) — менеджер не мог отличить возврат, чтобы запустить
MANAGER_RETURN_TO_WORK / MANAGER_FORCE_ACCEPT.

PR7 (минимальный объём): аутентифицированные app-эндпоинты
(kanban / список / детали / PATCH — все через `_make_request_card`) отдают
КАНОН «Возвращена»; публичная витрина и InfraSafe (отдельные пути,
`project_public_status` / `project_infrasafe_status`) — по-прежнему
проецируют в «Исполнено».
"""
import pytest

from uk_management_bot.database.models.request import Request as RequestModel


async def _seed_returned(db_session, rn: str, user_id: int):
    """Канон-возврат после cutover: status='Возвращена' напрямую."""
    req = RequestModel(
        request_number=rn,
        user_id=user_id,
        category="Сантехника",
        description="returned request",
        status="Возвращена",
        is_returned=True,
        return_reason="не устранена течь",
        source="web",
        media_files=[],
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)
    return req


@pytest.mark.asyncio
async def test_kanban_shows_returned_as_canon(client, db_session, manager_user):
    """Возвращённая заявка попадает в колонку «Возвращена», а не «Исполнено»."""
    await _seed_returned(db_session, "260611-001", manager_user.id)

    resp = await client.get("/api/v2/requests/kanban")
    assert resp.status_code == 200
    cols = {c["status"]: c for c in resp.json()["columns"]}

    assert "Возвращена" in cols, "kanban должен иметь колонку «Возвращена»"
    returned_nums = {r["request_number"] for r in cols["Возвращена"]["requests"]}
    assert "260611-001" in returned_nums

    completed_nums = {r["request_number"] for r in cols.get("Исполнено", {}).get("requests", [])}
    assert "260611-001" not in completed_nums, "канон не должен сворачиваться в «Исполнено» для менеджера"


@pytest.mark.asyncio
async def test_request_detail_shows_returned_canon(client, db_session, manager_user):
    """GET /requests/{rn} отдаёт реальный статус «Возвращена» + причину."""
    await _seed_returned(db_session, "260611-002", manager_user.id)

    resp = await client.get("/api/v2/requests/260611-002")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "Возвращена"
    assert body["return_reason"] == "не устранена течь"


@pytest.mark.asyncio
async def test_public_board_still_projects_returned(client, db_session, manager_user):
    """Публичная витрина (отдельный путь) НЕ раскрывает «Возвращена» наружу."""
    await _seed_returned(db_session, "260611-003", manager_user.id)

    resp = await client.get("/api/v2/public/board")
    assert resp.status_code == 200
    body = resp.json()
    assert "Возвращена" not in body["status_counts"], "новый wire-статус не должен течь на публичную витрину"
    active_statuses = {r["status"] for r in body["active_requests"]}
    assert "Возвращена" not in active_statuses
