"""РЕАЛЬНЫЕ гонки визуальных отчётов против PostgreSQL (паттерн
test_materials_pg_concurrency.py / PR-5 outbox).

SQLite не умеет row-locking (`FOR UPDATE` молча выбрасывается) и не даёт
настоящих параллельных транзакций, поэтому sqlite-сюиты в
`test_work_reports_saga.py` проверяют только последовательные подмены статуса.
Здесь — подлинный Postgres и три гонки, каждая из которых на sqlite
непроверяема:

  (а) два конкурентных `sync_pending_drafts` — ровно одна строка отчёта, без
      IntegrityError (диалектный ``INSERT ... ON CONFLICT DO NOTHING``);
  (б) два конкурентных `publish_report` одного отчёта — ровно один
      `published`, второй получает 409 (``SELECT ... FOR UPDATE`` в
      `_load_report_for_update` сериализует переход);
  (в) РЕГРЕССИЯ: конкурентные `PATCH` и `publish` одного отчёта не могут
      разъехать замороженный состав медиа. До добавления `with_for_update()`
      в `patch_work_report` проверка статуса была TOCTOU: publish успевал
      пройти целиком внутри окна `validate_media_ids` (сетевой вызов в
      media-service), после чего PATCH дописывал свои id уже в
      ОПУБЛИКОВАННЫЙ отчёт. Итог был: наружу отдавался media_id без
      publication-lock и без записи в media_meta, а вытесненный id оставался
      залоченным навсегда (reconcile не видел его осиротевшим, потому что
      locked_media_ids всё ещё его перечислял).

Изоляция: собственная temp-схема в той же БД (schema_translate_map).
Скип, если DATABASE_URL не Postgres (см. POSTGRES_TEST_URL в conftest).
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.session import Base
from uk_management_bot.services.work_report_service import (
    WorkReportPublishError,
    autopublish_ready_drafts,
    publish_report,
    sync_pending_drafts,
)

SCHEMA = "work_reports_race_test"

_TABLES = [
    User.__table__,
    Yard.__table__,
    Building.__table__,
    Apartment.__table__,
    Request.__table__,
    WorkReport.__table__,
    AuditLog.__table__,
    BoardConfig.__table__,
]

REQUEST_NUMBER = "260725-800"


def _pg_url() -> str | None:
    url = os.getenv("POSTGRES_TEST_URL", "")
    if not url.startswith("postgresql"):
        return None
    return url.replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture
async def pg_factory():
    url = _pg_url()
    if url is None:
        pytest.skip("DATABASE_URL is not PostgreSQL — real-race suite skipped")

    engine = create_async_engine(
        url,
        execution_options={"schema_translate_map": {None: SCHEMA}},
        pool_size=10,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
            await conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
            await conn.run_sync(lambda sc: Base.metadata.create_all(sc, tables=_TABLES))
    except Exception as exc:  # pragma: no cover — хост без доступного PG
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


def _photo(media_id: int) -> dict:
    return {
        "id": media_id,
        "file_type": "photo",
        "status": "active",
        "file_size": 1024,
        "mime_type": "image/jpeg",
    }


class FakeMediaClient:
    """Минимальный media_client для саги. `acquire_delay` растягивает окно
    между шагами публикации, чтобы гонка была наблюдаемой, а не зависела от
    случайного планирования."""

    def __init__(self, acquire_delay: float = 0.0):
        self._acquire_delay = acquire_delay
        self.acquired: list[int] = []
        self.released: list[int] = []

    async def get_request_media(self, request_number, category=None, limit=50):
        return {
            "request_photo": [_photo(1), _photo(2), _photo(99)],
            "completion_photo": [_photo(10), _photo(11)],
        }.get(category, [])

    async def acquire_publication_lock(self, media_id: int) -> bool:
        if self._acquire_delay:
            await asyncio.sleep(self._acquire_delay)
        self.acquired.append(media_id)
        return True

    async def release_publication_lock(self, media_id: int) -> bool:
        self.released.append(media_id)
        return True

    async def list_publication_locks(self, limit=200, offset=0):
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    async def resolve_stale_transitions(self, older_than_minutes: int = 15):
        return {}


async def _seed_request(factory, *, with_autopost: bool = False) -> int:
    """user + двор + дом + заявка уровня дома в статусе «Исполнено»."""
    async with factory() as db:
        user = User(
            telegram_id=424243, username="wrrace", first_name="Race",
            roles='["manager"]', active_role="manager", status="approved",
        )
        db.add(user)
        await db.flush()
        yard = Yard(name="Двор гонки")
        db.add(yard)
        await db.flush()
        building = Building(address="ул. Гоночная, 7", yard_id=yard.id)
        db.add(building)
        await db.flush()
        db.add(Request(
            request_number=REQUEST_NUMBER, user_id=user.id, category="plumbing",
            status="Исполнено", description="гонка", urgency="low",
            is_returned=False, address_type="building", building_id=building.id,
            updated_at=datetime.now(timezone.utc),
        ))
        if with_autopost:
            data = dict(DEFAULT_BOARD_CONFIG)
            data["work_reports"] = {
                "autopost": True,
                # Стамп в прошлом, но внутри 14-дневного потолка бэкфилла.
                "autopost_since": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "limit": 6,
                "title": {"ru": "", "uz": ""},
            }
            db.add(BoardConfig(id=1, data=data, updated_by=user.id))
        user_id = user.id
        await db.commit()
    return user_id


async def _mk_report(factory, *, before: list[int], after: list[int]) -> int:
    async with factory() as db:
        report = WorkReport(
            request_number=REQUEST_NUMBER, category_key="plumbing",
            address_public="ул. Гоночная, 7 (Двор гонки)",
            performed_at=datetime.now(timezone.utc),
            before_media_ids=before, after_media_ids=after,
            media_meta=[], locked_media_ids=[], status="pending", source="auto",
        )
        db.add(report)
        await db.commit()
        return report.id


# ===========================================================================
# (а) два конкурентных sync — ON CONFLICT DO NOTHING, а не IntegrityError
# ===========================================================================


@pytest.mark.asyncio
async def test_two_concurrent_syncs_create_exactly_one_row(pg_factory):
    await _seed_request(pg_factory, with_autopost=True)

    async def _sync():
        async with pg_factory() as db:
            return await sync_pending_drafts(db)

    results = await asyncio.gather(_sync(), _sync(), return_exceptions=True)

    # Ни один из вызовов не должен упасть — идемпотентность обеспечена
    # ON CONFLICT, а не «повезло с порядком».
    assert [r for r in results if isinstance(r, Exception)] == []
    async with pg_factory() as db:
        total = (await db.execute(
            select(func.count()).select_from(WorkReport)
            .where(WorkReport.request_number == REQUEST_NUMBER)
        )).scalar_one()
    assert total == 1
    # Ровно один из двух вызовов записал строку.
    assert sum(r["created"] for r in results) == 1


# ===========================================================================
# (б) два конкурентных publish — один published, второй 409
# ===========================================================================


@pytest.mark.asyncio
async def test_two_concurrent_publishes_one_wins_other_409(pg_factory):
    await _seed_request(pg_factory)
    report_id = await _mk_report(pg_factory, before=[1], after=[10])

    async def _publish():
        async with pg_factory() as db:
            return await publish_report(
                db, FakeMediaClient(acquire_delay=0.05), report_id, moderator_id=None
            )

    results = await asyncio.gather(_publish(), _publish(), return_exceptions=True)

    conflicts = [r for r in results if isinstance(r, WorkReportPublishError)]
    winners = [r for r in results if isinstance(r, WorkReport)]
    assert len(winners) == 1, results
    assert len(conflicts) == 1, results
    assert conflicts[0].status_code == 409

    async with pg_factory() as db:
        row = (await db.execute(
            select(WorkReport).where(WorkReport.id == report_id)
        )).scalar_one()
    assert row.status == "published"
    # Замороженный состав согласован: что отдаётся — то и залочено.
    assert set(row.before_media_ids) | set(row.after_media_ids) == set(row.locked_media_ids)


# ===========================================================================
# (в) РЕГРЕССИЯ: PATCH против publish не разъезжает замороженный состав
# ===========================================================================


@pytest.mark.asyncio
async def test_concurrent_patch_and_publish_keep_frozen_media_consistent(
    pg_factory, monkeypatch
):
    """Вызываем НАСТОЯЩИЙ обработчик PATCH (не переизобретаем его логику в
    тесте — иначе проверялся бы тест, а не код) параллельно с публикацией.

    Чередование сделано ДЕТЕРМИНИРОВАННЫМ, иначе тест «проходит» и на сломанном
    коде: гейт держит PATCH ровно там, где у него реальное окно — на
    `validate_media_ids` (сетевой вызов в media-service) — между чтением строки
    и записью. Гейт с таймаутом, а не ожиданием публикации: с корректным
    `with_for_update()` PATCH уже держит row-lock, публикация ждёт его, и
    безусловное ожидание дало бы взаимную блокировку.

    Победителя намеренно не фиксируем — он зависит от того, кто взял lock.
    Фиксируем ИНВАРИАНТ, который lock и защищает: у опубликованного отчёта
    множество отдаваемых наружу id совпадает с множеством залоченных, и
    media_meta покрывает их все.
    """
    import contextlib

    from uk_management_bot.api.work_reports import router as wr_router
    from uk_management_bot.api.work_reports.schemas import WorkReportPatchIn
    from uk_management_bot.services import work_report_service

    await _seed_request(pg_factory)
    report_id = await _mk_report(pg_factory, before=[1], after=[10])

    media = FakeMediaClient(acquire_delay=0.02)
    monkeypatch.setattr(wr_router, "get_media_client", lambda: media)

    publish_done = asyncio.Event()
    original_validate = work_report_service.validate_media_ids

    async def gated_validate(media_client, request_number, before_media_ids, after_media_ids):
        # 99 приходит только из PATCH — публикацию (она валидирует сохранённые
        # [1]/[10] или уже применённые PATCH'ем) не задерживаем.
        if 99 in before_media_ids:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(publish_done.wait(), timeout=2.0)
        return await original_validate(
            media_client, request_number, before_media_ids, after_media_ids
        )

    monkeypatch.setattr(work_report_service, "validate_media_ids", gated_validate)

    user = type("U", (), {"id": None})()

    async def _patch():
        async with pg_factory() as db:
            return await wr_router.patch_work_report(
                report_id, WorkReportPatchIn(before_media_ids=[99]), db, user
            )

    async def _publish():
        # Даём PATCH'у гарантированно дойти до своего чтения строки первым —
        # именно этот порядок и вскрывал гонку.
        await asyncio.sleep(0.05)
        try:
            async with pg_factory() as db:
                return await publish_report(db, media, report_id, moderator_id=None)
        finally:
            publish_done.set()

    results = await asyncio.gather(_patch(), _publish(), return_exceptions=True)

    async with pg_factory() as db:
        row = (await db.execute(
            select(WorkReport).where(WorkReport.id == report_id)
        )).scalar_one()

    served = set(row.before_media_ids) | set(row.after_media_ids)
    if row.status == "published":
        assert served == set(row.locked_media_ids), (
            f"опубликован состав {served}, залочен {set(row.locked_media_ids)} — "
            "наружу уходит id без publication-lock"
        )
        assert served == {m["id"] for m in row.media_meta}, (
            "media_meta не покрывает отдаваемые id — Content-Type свалится "
            "в application/octet-stream"
        )
    else:
        # PATCH успел первым и удержал лок: publish обязан был получить 409,
        # а не опубликовать отчёт с наполовину применённой правкой.
        assert row.status in ("pending", "needs_media"), row.status
        assert any(
            isinstance(r, WorkReportPublishError) and r.status_code == 409
            for r in results
        ), results


# ===========================================================================
# (г) AUD6-P1-3: батч автопубликации в сети НЕ блокирует параллельный publish
# ===========================================================================


class GatedFetchMediaClient(FakeMediaClient):
    """`get_request_media` замирает до `gate` — моделирует деградировавший
    media-service ровно в сетевой фазе автозаполнения батча."""

    def __init__(self):
        super().__init__()
        self.gate = asyncio.Event()
        self.fetch_started = asyncio.Event()

    async def get_request_media(self, request_number, category=None, limit=50):
        self.fetch_started.set()
        await self.gate.wait()
        return await super().get_request_media(request_number, category, limit)


@pytest.mark.asyncio
async def test_autopublish_stuck_in_network_does_not_block_publish(pg_factory):
    """Регрессия AUD6-P1-3: раньше `autopublish_ready_drafts` брал FOR UPDATE
    сразу на всех кандидатах и держал транзакцию через сетевые вызовы — у
    менеджера, жмущего «Опубликовать» в этот момент, запрос вставал в очередь
    за всем пакетом (до минут при недоступном media). Теперь кандидаты
    выбираются без лока, сеть идёт до лока: ручной publish обязан пройти,
    пока батч висит в media-service."""
    await _seed_request(pg_factory)
    report_id = await _mk_report(pg_factory, before=[1], after=[10])

    # Конфиг с включённой автопубликацией — иначе батч выйдет сразу.
    async with pg_factory() as db:
        data = dict(DEFAULT_BOARD_CONFIG)
        data["work_reports"] = {**data["work_reports"], "autopublish": True}
        db.add(BoardConfig(id=1, data=data, updated_by=None))
        await db.commit()

    slow = GatedFetchMediaClient()

    async def _batch():
        async with pg_factory() as db:
            return await autopublish_ready_drafts(db, slow, triggered_by=None)

    batch_task = asyncio.create_task(_batch())

    # Батч «в сети». Ручная публикация того же отчёта обязана пройти, не
    # дожидаясь его: под старым кодом этот wait_for падал TimeoutError —
    # строка отчёта была под батчевым FOR UPDATE.
    async def _manual_publish():
        async with pg_factory() as db:
            return await publish_report(
                db, FakeMediaClient(), report_id, moderator_id=None
            )

    try:
        await asyncio.wait_for(slow.fetch_started.wait(), timeout=5)
        published = await asyncio.wait_for(_manual_publish(), timeout=5)
        assert published.status == "published"
    finally:
        # gate — в finally: иначе на регрессировавшем коде (publish завис под
        # батчевым локом) батч вечно ждал бы сеть, teardown вечно ждал бы батч,
        # и вместо красного теста CI съедал бы таймаут всей джобы. Проверено
        # прогоном против старого кода: с finally тест падает за секунды.
        slow.gate.set()

    # Per-report перепроверка батча под локом обязана увидеть, что строка уже
    # не pending, и молча пропустить её — не перезаписав состав опубликованного
    # отчёта и не уронив пакет.
    result = await asyncio.wait_for(batch_task, timeout=10)
    assert result["enabled"] is True
    assert result["published"] == 0
    assert result["failed"] == 0

    async with pg_factory() as db:
        row = (await db.execute(
            select(WorkReport).where(WorkReport.id == report_id)
        )).scalar_one()
    assert row.status == "published"
    assert row.locked_media_ids == [1, 10], "батч не должен трогать опубликованный состав"
