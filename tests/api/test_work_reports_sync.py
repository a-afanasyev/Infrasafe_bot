"""Тесты `work_report_service.sync_pending_drafts` (T5).

Автосоздание WorkReport-черновиков из завершённых заявок — идемпотентно
(dialect-aware ON CONFLICT DO NOTHING, паттерн webhook_sender), с двойным
floor (autopost_since / 14 дней) и circuit breaker на 200 pending/needs_media
строк.
"""
import copy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.work_report_service import sync_pending_drafts

def _UTC_NOW() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_board_config(
    db: AsyncSession,
    *,
    autopost: bool,
    autopost_since: datetime | None,
    categories: list[str] | None = None,
    autopublish: bool = False,
) -> None:
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["work_reports"]["autopost"] = autopost
    data["work_reports"]["autopost_since"] = (
        autopost_since.isoformat() if autopost_since is not None else None
    )
    data["work_reports"]["autopublish"] = autopublish
    data["work_reports"]["categories"] = categories if categories is not None else []
    db.add(BoardConfig(id=1, data=data, updated_by=None))
    await db.commit()


async def _mk_yard(db: AsyncSession, name: str) -> Yard:
    yard = Yard(name=name)
    db.add(yard)
    await db.commit()
    await db.refresh(yard)
    return yard


async def _mk_building(db: AsyncSession, yard_id: int, address: str) -> Building:
    building = Building(address=address, yard_id=yard_id)
    db.add(building)
    await db.commit()
    await db.refresh(building)
    return building


async def _mk_request(
    db: AsyncSession,
    number: str,
    *,
    status: str = "Принято",
    is_returned: bool = False,
    address_type: str | None = "yard",
    yard_id: int | None = None,
    building_id: int | None = None,
    apartment_id: int | None = None,
    completed_at: datetime | None = None,
    updated_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Request:
    req = Request(
        request_number=number,
        user_id=1,
        category="plumbing",
        status=status,
        description="test",
        urgency="low",
        is_returned=is_returned,
        address_type=address_type,
        yard_id=yard_id,
        building_id=building_id,
        apartment_id=apartment_id,
        completed_at=completed_at,
        updated_at=updated_at,
    )
    if created_at is not None:
        req.created_at = created_at
    db.add(req)
    await db.commit()
    return req


async def _existing_report_numbers(db: AsyncSession) -> set[str]:
    rows = (await db.execute(select(WorkReport.request_number))).scalars().all()
    return set(rows)


# ── Basic eligibility ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_creates_draft_for_eligible_yard_request(db_session: AsyncSession):
    yard = await _mk_yard(db_session, "Двор А")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    await _mk_request(
        db_session, "260725-001", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=_UTC_NOW(),
    )

    result = await sync_pending_drafts(db_session)

    assert result == {"created": 1, "circuit_breaker": False}
    report = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-001")
        )
    ).scalar_one()
    assert report.status == "pending"
    assert report.source == "auto"
    assert report.address_public == "Двор А"


@pytest.mark.asyncio
async def test_excludes_legacy_and_null_address_type(db_session: AsyncSession):
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    await _mk_request(
        db_session, "260725-010", status="Принято", address_type="legacy",
        completed_at=_UTC_NOW(),
    )
    await _mk_request(
        db_session, "260725-011", status="Принято", address_type=None,
        completed_at=_UTC_NOW(),
    )

    result = await sync_pending_drafts(db_session)

    assert result["created"] == 0
    assert await _existing_report_numbers(db_session) == set()


@pytest.mark.asyncio
async def test_includes_yard_level_request(db_session: AsyncSession):
    yard = await _mk_yard(db_session, "Двор Б")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    await _mk_request(
        db_session, "260725-020", status="Исполнено", address_type="yard", yard_id=yard.id,
        updated_at=_UTC_NOW(),
    )

    result = await sync_pending_drafts(db_session)

    assert result["created"] == 1
    assert "260725-020" in await _existing_report_numbers(db_session)


@pytest.mark.asyncio
async def test_excludes_self_declared_status_vypolnena(db_session: AsyncSession):
    """"Выполнена" (self-declared by executor) is deliberately excluded —
    only manager-reviewed statuses (Исполнено/Принято) are eligible."""
    yard = await _mk_yard(db_session, "Двор В")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    await _mk_request(
        db_session, "260725-030", status="Выполнена", address_type="yard", yard_id=yard.id,
        updated_at=_UTC_NOW(),
    )

    result = await sync_pending_drafts(db_session)

    assert result["created"] == 0


@pytest.mark.asyncio
async def test_excludes_returned_request(db_session: AsyncSession):
    yard = await _mk_yard(db_session, "Двор Г")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    await _mk_request(
        db_session, "260725-040", status="Принято", is_returned=True,
        address_type="yard", yard_id=yard.id, completed_at=_UTC_NOW(),
    )

    result = await sync_pending_drafts(db_session)

    assert result["created"] == 0


# ── Floor: autopost_since vs 14-days-ago, whichever is later binds ─────


@pytest.mark.asyncio
async def test_autopost_since_is_the_binding_floor(db_session: AsyncSession):
    """autopost_since is recent (2 days ago) — later than "14 days ago" — so
    it's the binding floor: a request just before autopost_since (but well
    within the last 14 days) must still be excluded."""
    yard = await _mk_yard(db_session, "Двор Д")
    since = _UTC_NOW() - timedelta(days=2)
    await _seed_board_config(db_session, autopost=True, autopost_since=since)

    await _mk_request(
        db_session, "260725-050", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=since + timedelta(hours=1),
    )
    await _mk_request(
        db_session, "260725-051", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=since - timedelta(days=1),  # 3 days ago: within 14d, before autopost_since
    )

    result = await sync_pending_drafts(db_session)

    assert result["created"] == 1
    numbers = await _existing_report_numbers(db_session)
    assert numbers == {"260725-050"}


@pytest.mark.asyncio
async def test_fourteen_days_ago_is_the_binding_floor(db_session: AsyncSession):
    """autopost_since is old (30 days ago) — older than "14 days ago" — so
    the 14-day floor binds instead: a request from 20 days ago must be
    excluded even though it's after autopost_since."""
    yard = await _mk_yard(db_session, "Двор Е")
    since = _UTC_NOW() - timedelta(days=30)
    await _seed_board_config(db_session, autopost=True, autopost_since=since)

    await _mk_request(
        db_session, "260725-060", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=_UTC_NOW() - timedelta(days=10),
    )
    await _mk_request(
        db_session, "260725-061", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=_UTC_NOW() - timedelta(days=20),
    )

    result = await sync_pending_drafts(db_session)

    assert result["created"] == 1
    numbers = await _existing_report_numbers(db_session)
    assert numbers == {"260725-060"}


# ── Circuit breaker ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_circuit_breaker_at_200_pending_rows(db_session: AsyncSession):
    yard = await _mk_yard(db_session, "Двор Ж")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))

    for i in range(200):
        db_session.add(WorkReport(
            request_number=f"seed-{i:04d}",
            category_key="plumbing",
            address_public="dummy",
            performed_at=_UTC_NOW(),
            status="pending" if i % 2 == 0 else "needs_media",
            source="auto",
        ))
    await db_session.commit()

    await _mk_request(
        db_session, "260725-070", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=_UTC_NOW(),
    )

    result = await sync_pending_drafts(db_session)

    assert result == {"created": 0, "circuit_breaker": True}
    assert "260725-070" not in await _existing_report_numbers(db_session)


# ── Idempotency ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calling_twice_creates_exactly_one_row(db_session: AsyncSession):
    yard = await _mk_yard(db_session, "Двор З")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    await _mk_request(
        db_session, "260725-080", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=_UTC_NOW(),
    )

    first = await sync_pending_drafts(db_session)
    second = await sync_pending_drafts(db_session)

    assert first["created"] == 1
    assert second["created"] == 0
    rows = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-080")
        )
    ).scalars().all()
    assert len(rows) == 1


# ── No-op when autopost disabled ────────────────────────────────────


@pytest.mark.asyncio
async def test_noop_when_autopost_disabled(db_session: AsyncSession):
    yard = await _mk_yard(db_session, "Двор И")
    await _seed_board_config(db_session, autopost=False, autopost_since=None)
    await _mk_request(
        db_session, "260725-090", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=_UTC_NOW(),
    )

    result = await sync_pending_drafts(db_session)

    assert result == {"created": 0, "circuit_breaker": False}
    assert await _existing_report_numbers(db_session) == set()


# ── performed_at fallback chain ─────────────────────────────────────


@pytest.mark.asyncio
async def test_performed_at_uses_updated_at_fallback_for_ispolneno(db_session: AsyncSession):
    """"Исполнено" leaves completed_at NULL — anchor must fall back to
    updated_at."""
    yard = await _mk_yard(db_session, "Двор К")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    marker = _UTC_NOW() - timedelta(hours=3)
    await _mk_request(
        db_session, "260725-100", status="Исполнено", address_type="yard", yard_id=yard.id,
        completed_at=None, updated_at=marker,
    )

    result = await sync_pending_drafts(db_session)
    assert result["created"] == 1

    report = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-100")
        )
    ).scalar_one()
    assert report.performed_at is not None
    # sqlite drops tzinfo on round-trip — compare naive.
    assert abs((report.performed_at.replace(tzinfo=None) - marker.replace(tzinfo=None)).total_seconds()) < 2


@pytest.mark.asyncio
async def test_performed_at_uses_completed_at_for_prinyato(db_session: AsyncSession):
    """"Принято" sets completed_at — anchor must use it directly, not
    updated_at/created_at."""
    yard = await _mk_yard(db_session, "Двор Л")
    await _seed_board_config(db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1))
    marker = _UTC_NOW() - timedelta(hours=5)
    later = _UTC_NOW() - timedelta(hours=1)
    await _mk_request(
        db_session, "260725-110", status="Принято", address_type="yard", yard_id=yard.id,
        completed_at=marker, updated_at=later,
    )

    result = await sync_pending_drafts(db_session)
    assert result["created"] == 1

    report = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-110")
        )
    ).scalar_one()
    assert abs((report.performed_at.replace(tzinfo=None) - marker.replace(tzinfo=None)).total_seconds()) < 2


# ── Фильтр категорий (work_reports.categories) НЕ действует на синк ──
#
# Список ограничивает только автопубликацию (`autopublish_ready_drafts`, тесты в
# test_work_reports_saga.py). Очередь модерации наполняется по всем подходящим
# заявкам — см. тест ниже.


@pytest.mark.asyncio
async def test_sync_ignores_category_filter(db_session: AsyncSession):
    """Черновик создаётся и для категории вне списка.

    Раньше фильтр стоял здесь, и это было необратимо: заявка вне списка не
    получала черновика, уезжала из 14-дневного окна `floor_ts` и после снятия
    галочки уже не подхватывалась — в отличие от черновика, который просто
    ждёт в очереди. Плюс подпись в UI обещает «остальные отчёты остаются на
    модерации». Что уйдёт в ленту без человека — решает автопубликация.
    """
    await _seed_board_config(
        db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1),
        categories=["cleaning"],
    )
    yard = await _mk_yard(db_session, "Двор")
    await _mk_request(db_session, "260725-401", yard_id=yard.id, updated_at=_UTC_NOW())
    req = await _mk_request(db_session, "260725-402", yard_id=yard.id, updated_at=_UTC_NOW())
    req.category = "cleaning"
    await db_session.commit()

    await sync_pending_drafts(db_session)

    # 401 — plumbing (вне списка), 402 — cleaning (в списке): в очереди ОБА.
    assert await _existing_report_numbers(db_session) == {"260725-401", "260725-402"}


@pytest.mark.asyncio
async def test_legacy_russian_category_label_snapshots_canonical_key(db_session: AsyncSession):
    """`Request.category` у старых строк хранит RU-подпись, а не канон-ключ.

    В снапшот отчёта обязан попасть канон-ключ (`resolve_category_key`): по нему
    сравнивает фильтр автопубликации и его рендерит публичная лента. Список
    категорий задан намеренно — заодно фиксируем, что синк на него не смотрит.
    """
    await _seed_board_config(
        db_session, autopost=True, autopost_since=_UTC_NOW() - timedelta(days=1),
        categories=["plumbing"],
    )
    yard = await _mk_yard(db_session, "Двор")
    req = await _mk_request(db_session, "260725-403", yard_id=yard.id, updated_at=_UTC_NOW())
    req.category = "Уборка"  # легаси-подпись категории cleaning
    await db_session.commit()

    await sync_pending_drafts(db_session)

    numbers = await _existing_report_numbers(db_session)
    assert numbers == {"260725-403"}
    report = (await db_session.execute(select(WorkReport))).scalars().one()
    assert report.category_key == "cleaning"
