"""Тесты services/auto_manager/orchestrator.py: AutoManagerOrchestrator.run_once.

Паттерн sqlite-фикстуры — как в test_auto_manager_rule_engine.py/
test_auto_manager_window.py; builders для User/Shift/Request/RequestAssignment
мирроят те же файлы. `run_command_sync` пишет через СВОЮ сессию (session_factory,
как auto_dispatch_new_request_sync в services/dispatch.py) — поэтому тесты
монтируют `orchestrator.SessionLocal` на тестовый sessionmaker, привязанный к
ТОМУ ЖЕ sqlite-engine, что и фикстура (in-memory sqlite = один connection на
поток → все сессии видят один и тот же набор данных).

Уведомления — через инжектируемый `bot`-дубль (FakeBot), а не реальный
Telegram (см. AutoManagerOrchestrator.__init__/_get_bot).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.services.auto_manager.orchestrator as orch_mod
import uk_management_bot.services.redis_pubsub as pubsub_mod
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.auto_manager.config import save_config_sync
from uk_management_bot.services.auto_manager.orchestrator import AutoManagerOrchestrator
from uk_management_bot.services.workflow_runner import WorkflowError
from uk_management_bot.utils.constants import REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_NEW

SPECIALIZATION = "plumber"
APPLICANT_ID = 999
SYSTEM_USER_ID = 9999

FIXED_NOW = datetime(2026, 7, 23, 2, 0, tzinfo=timezone.utc)  # overnight, inside a shift


class FakeBot:
    """Тестовый bot-дубль — фиксирует отправленные сообщения вместо реального Telegram."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


# ─────────────────────────── fixture: sqlite + shared session factory ───────────────────────────

@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    db.add(User(id=APPLICANT_ID, telegram_id=APPLICANT_ID, roles='["applicant"]', status="approved"))
    db.add(User(id=SYSTEM_USER_ID, telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID,
                roles='["applicant"]', status="approved"))
    db.commit()

    # orchestrator.py references SessionLocal/run_command_sync/select_executor as bare
    # module-level names — patching the module attribute redirects every call site.
    monkeypatch.setattr(orch_mod, "SessionLocal", TestSessionLocal)

    yield db, TestSessionLocal

    db.close()
    Base.metadata.drop_all(bind=engine)


def _always_active_config(db, **overrides):
    data = {"enabled": True, "window_start": "00:00", "window_end": "00:00",
            "max_requests_per_run": 10}
    data.update(overrides)
    save_config_sync(db, data)


def _executor(db, uid, tg, *, roles='["executor"]', status="approved", specialization=SPECIALIZATION,
              language="ru"):
    u = User(id=uid, telegram_id=tg, roles=roles, active_role="executor",
             status=status, specialization=specialization, language=language)
    db.add(u)
    db.commit()
    return u


def _manager(db, uid, tg, *, status="approved", language="ru"):
    u = User(id=uid, telegram_id=tg, roles='["manager"]', active_role="manager", status=status,
             language=language)
    db.add(u)
    db.commit()
    return u


def _shift(db, sid, user_id, *, status="active", specs=None, start=None, end=None):
    s = Shift(
        id=sid, user_id=user_id, status=status,
        start_time=start if start is not None else FIXED_NOW - timedelta(hours=1),
        end_time=end if end is not None else FIXED_NOW + timedelta(hours=6),
        specialization_focus=specs,
    )
    db.add(s)
    db.commit()
    return s


def _group_request(db, number, *, specialization=SPECIALIZATION, created_at=None,
                    created_by=SYSTEM_USER_ID, category="plumbing", address="Тестовый адрес"):
    """«В работе» + активное непривязанное групповое назначение (main-очередь)."""
    r = Request(
        request_number=number, user_id=APPLICANT_ID, category=category,
        description="desc", status=REQUEST_STATUS_IN_PROGRESS, executor_id=None,
        assignment_type="group", assigned_group=specialization,
        address=address, created_at=created_at or FIXED_NOW,
    )
    db.add(r)
    db.add(RequestAssignment(
        request_number=number, assignment_type="group",
        group_specialization=specialization, executor_id=None,
        status="active", created_by=created_by,
    ))
    db.commit()
    return r


def _residual_request(db, number, *, category="plumbing", created_at=None):
    """«Новая», без назначения вовсе (резидуальная очередь)."""
    r = Request(
        request_number=number, user_id=APPLICANT_ID, category=category,
        description="desc", status=REQUEST_STATUS_NEW, executor_id=None,
        assignment_type=None, assigned_group=None,
        address="Тестовый адрес", created_at=created_at or FIXED_NOW,
    )
    db.add(r)
    db.commit()
    return r


def _patch_publish(monkeypatch) -> list:
    """Collects (event_type, data) calls to publish_request_event.

    `_publish_kanban_refresh` does a LOCAL `from ...redis_pubsub import
    publish_request_event` inside the method body — patching the attribute
    on the `redis_pubsub` module itself (not on `orch_mod`) is what the local
    import actually resolves at call time.
    """
    calls: list = []

    async def fake_publish(event_type, data):
        calls.append((event_type, data))

    monkeypatch.setattr(pubsub_mod, "publish_request_event", fake_publish)
    return calls


def _refresh_request(session_factory, number) -> Request:
    """Свежее чтение (run_command_sync пишет ЧЕРЕЗ ДРУГУЮ сессию)."""
    fresh = session_factory()
    try:
        return fresh.query(Request).filter(Request.request_number == number).one()
    finally:
        fresh.close()


# ─────────────────────────── config gate ───────────────────────────

@pytest.mark.asyncio
async def test_disabled_config_is_noop(env, monkeypatch):
    db, TestSessionLocal = env
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)
    # DEFAULT_CONFIG.enabled == False — не сохраняем конфиг вовсе.

    _group_request(db, "260723-001")
    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id)

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    req = _refresh_request(TestSessionLocal, "260723-001")
    assert req.executor_id is None
    assert req.assignment_type == "group"
    assert fake_bot.sent == []
    assert orchestrator._retry_after == {}
    assert orchestrator._notified == {}


@pytest.mark.asyncio
async def test_outside_window_is_noop(env, monkeypatch):
    db, TestSessionLocal = env
    save_config_sync(db, {
        "enabled": True, "window_start": "20:00", "window_end": "08:00",
        "timezone": "UTC", "max_requests_per_run": 10,
    })
    # 12:00 UTC — вне окна 20:00-08:00.
    outside_now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: outside_now)

    _group_request(db, "260723-001")
    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id, start=outside_now - timedelta(hours=1), end=outside_now + timedelta(hours=6))

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    req = _refresh_request(TestSessionLocal, "260723-001")
    assert req.executor_id is None
    assert req.assignment_type == "group"
    assert fake_bot.sent == []


# ─────────────────────────── happy paths ───────────────────────────

@pytest.mark.asyncio
async def test_main_queue_happy_path_promotes_group_to_executor(env, monkeypatch):
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)
    publish_calls = _patch_publish(monkeypatch)

    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id)
    _group_request(db, "260723-101")

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    req = _refresh_request(TestSessionLocal, "260723-101")
    assert req.executor_id == ex.id
    assert req.assignment_type == "individual"
    assert req.assigned_group is None

    assert len(fake_bot.sent) == 1
    chat_id, text = fake_bot.sent[0]
    assert chat_id == ex.telegram_id
    assert "260723-101" in text

    # Kanban: group->individual promotion has no public status change, so
    # _build_events wouldn't emit a webhook/realtime intent even if the
    # discarded CommandOutcome were read — the orchestrator's OWN best-effort
    # "request.updated" publish is what keeps an open Kanban tab from showing
    # a stale executor.
    assert publish_calls == [("request.updated", {"number": "260723-101"})]


@pytest.mark.asyncio
async def test_notifies_executor_in_their_own_language_not_hardcoded_ru(env, monkeypatch):
    # Regression: notifications were hardcoded language="ru" regardless of
    # the recipient's actual User.language, even though UZ translations exist
    # for both notification keys.
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)

    ex = _executor(db, 1, 1001, language="uz")
    _shift(db, 1, ex.id)
    _group_request(db, "260723-106")

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    assert len(fake_bot.sent) == 1
    _, text = fake_bot.sent[0]
    # UZ string for auto_manager.assigned_notification (config/locales/uz.json).
    assert "Sizga ariza tayinlandi" in text
    assert "Назначена заявка" not in text


@pytest.mark.asyncio
async def test_notifies_manager_in_their_own_language_no_duty(env, monkeypatch):
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)

    _manager(db, 2, 2002, language="uz")
    _group_request(db, "260723-107")
    # Нет ни одного исполнителя вовсе.

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    assert len(fake_bot.sent) == 1
    _, text = fake_bot.sent[0]
    # UZ string for auto_manager.no_duty_executor (config/locales/uz.json).
    assert "Navbatchi ijrochi topilmadi" in text


@pytest.mark.asyncio
async def test_executor_notification_escapes_html_special_chars_in_address(env, monkeypatch):
    # Regression: req.address is free user-entered text interpolated into a
    # parse_mode="HTML" Telegram message — unescaped `<`/`>`/`&` could break
    # message delivery (Telegram rejects malformed HTML entities/tags).
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)

    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id)
    _group_request(db, "260723-108", address="ул. Тест <b>1</b> & Co, кв. №2>3")

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    assert len(fake_bot.sent) == 1
    _, text = fake_bot.sent[0]
    assert "<b>1</b>" not in text  # raw tag must not survive unescaped
    assert "&lt;b&gt;1&lt;/b&gt;" in text
    assert "&amp;" in text
    assert "&gt;3" in text


@pytest.mark.asyncio
async def test_residual_queue_happy_path_assigns_individual(env, monkeypatch):
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)
    publish_calls = _patch_publish(monkeypatch)

    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id)
    _residual_request(db, "260723-102", category="plumbing")

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    req = _refresh_request(TestSessionLocal, "260723-102")
    assert req.status == REQUEST_STATUS_IN_PROGRESS
    assert req.executor_id == ex.id
    assert req.assignment_type == "individual"

    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0][0] == ex.telegram_id

    assert publish_calls == [("request.updated", {"number": "260723-102"})]


# ─────────────────────────── no duty available ───────────────────────────

@pytest.mark.asyncio
async def test_main_queue_no_duty_leaves_assignment_untouched_and_notifies_managers(env, monkeypatch):
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)
    publish_calls = _patch_publish(monkeypatch)

    mgr = _manager(db, 2, 2002)
    _group_request(db, "260723-103")
    # Нет ни одного исполнителя вовсе.

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    req = _refresh_request(TestSessionLocal, "260723-103")
    assert req.executor_id is None
    assert req.assignment_type == "group"
    assert req.assigned_group == SPECIALIZATION

    assert "260723-103" in orchestrator._retry_after
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0][0] == mgr.telegram_id

    # Nothing was written (no candidate at all) — no Kanban-refresh publish.
    assert publish_calls == []


@pytest.mark.asyncio
async def test_residual_queue_no_duty_falls_back_to_group_dispatch(env, monkeypatch):
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)
    publish_calls = _patch_publish(monkeypatch)

    mgr = _manager(db, 2, 2002)
    _residual_request(db, "260723-104", category="plumbing")
    # Нет ни одного исполнителя вовсе.

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    req = _refresh_request(TestSessionLocal, "260723-104")
    # Резидуальный group-dispatch: Новая -> В работе, groupнеустановленным исполнителем.
    assert req.status == REQUEST_STATUS_IN_PROGRESS
    assert req.executor_id is None
    assert req.assignment_type == "group"
    assert req.assigned_group == SPECIALIZATION

    assert "260723-104" in orchestrator._retry_after
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0][0] == mgr.telegram_id

    # Новая->В работе IS a genuine public status change even in the no-duty
    # fallback — Kanban must still refetch.
    assert publish_calls == [("request.updated", {"number": "260723-104"})]


# ─────────────────────────── manager-notification dedup ───────────────────────────

@pytest.mark.asyncio
async def test_manager_notification_dedup_within_12h_window(env, monkeypatch):
    db, TestSessionLocal = env
    _always_active_config(db)
    mgr = _manager(db, 2, 2002)
    _group_request(db, "260723-105")

    current = {"now": FIXED_NOW}
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: current["now"])

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)

    await orchestrator.run_once()
    assert len(fake_bot.sent) == 1

    # 20 минут спустя: cooldown (15 мин) истёк → заявка переобрабатывается,
    # но dedup (_notified, TTL 12ч) не даёт слать повторно.
    current["now"] = FIXED_NOW + timedelta(minutes=20)
    await orchestrator.run_once()

    assert len(fake_bot.sent) == 1  # НЕ 2
    assert fake_bot.sent[0][0] == mgr.telegram_id


# ─────────────────────────── WorkflowError race ───────────────────────────

@pytest.mark.asyncio
async def test_workflow_error_race_skips_gracefully_and_tick_continues(env, monkeypatch):
    db, TestSessionLocal = env
    _always_active_config(db)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)
    publish_calls = _patch_publish(monkeypatch)

    ex = _executor(db, 1, 1001)
    _shift(db, 1, ex.id)

    RACE_REQ = "260723-201"
    OK_REQ = "260723-202"
    _group_request(db, RACE_REQ, created_at=FIXED_NOW - timedelta(hours=2))
    _group_request(db, OK_REQ, created_at=FIXED_NOW - timedelta(hours=1))

    # Симулируем гонку: между выбором кандидата (select_executor) и записью
    # (run_command_sync) менеджер (или другой процесс) успел переназначить
    # RACE_REQ — run_command_sync в реальности вернул бы WorkflowError
    # (rowcount-guard promote_group_assignment/authorize). Здесь мы форсируем
    # ровно этот исход для RACE_REQ, не трогая нормальный путь для OK_REQ.
    original_run_command_sync = orch_mod.run_command_sync

    def racing_run_command_sync(session_factory, request_number, principal, command, now=None):
        if request_number == RACE_REQ:
            raise WorkflowError("simulated race: already reassigned")
        return original_run_command_sync(session_factory, request_number, principal, command, now=now)

    monkeypatch.setattr(orch_mod, "run_command_sync", racing_run_command_sync)

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    race_req = _refresh_request(TestSessionLocal, RACE_REQ)
    assert race_req.executor_id is None
    assert race_req.assignment_type == "group"  # нетронуто

    ok_req = _refresh_request(TestSessionLocal, OK_REQ)
    assert ok_req.executor_id == ex.id
    assert ok_req.assignment_type == "individual"

    # WorkflowError-путь НЕ ставит cooldown и НЕ шлёт менеджерам.
    assert RACE_REQ not in orchestrator._retry_after
    assert orchestrator._notified == {}
    # Единственное сообщение — исполнителю по OK_REQ.
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0][0] == ex.telegram_id

    # Kanban-publish only for the genuine write (OK_REQ) — NOT for the raced
    # RACE_REQ (nothing was actually written there, publishing would be a
    # false "something changed" signal).
    assert publish_calls == [("request.updated", {"number": OK_REQ})]


# ─────────────────────────── anti-starvation: cursor wrap-around ───────────────────────────

@pytest.mark.asyncio
async def test_anti_starvation_cursor_visits_every_no_duty_request(env, monkeypatch):
    """9 no-duty заявок, слотов на тик — 4 (< N). За 3 тика курсор обязан
    посетить ВСЕ 9 (включая тик, где forward-scan возвращает < slots и
    срабатывает wrap-around-ветка), а не застревать на первых 4."""
    db, TestSessionLocal = env
    _always_active_config(db, max_requests_per_run=4)

    numbers = [f"260723-{i:03d}" for i in range(1, 10)]
    for i, number in enumerate(numbers):
        _group_request(db, number, specialization="obscure_spec",
                       created_at=FIXED_NOW + timedelta(seconds=i))
    # Ни одного исполнителя со специализацией "obscure_spec" — все 9 всегда no-duty.

    current = {"now": FIXED_NOW}
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: current["now"])

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)

    await orchestrator.run_once()
    assert len(orchestrator._retry_after) == 4

    current["now"] = FIXED_NOW + timedelta(minutes=1)
    await orchestrator.run_once()
    assert len(orchestrator._retry_after) == 8

    current["now"] = FIXED_NOW + timedelta(minutes=2)
    await orchestrator.run_once()
    assert len(orchestrator._retry_after) == 9
    assert set(orchestrator._retry_after.keys()) == set(numbers)


@pytest.mark.asyncio
async def test_anti_starvation_phase2_reclaims_after_cooldown_expiry(env, monkeypatch):
    """Прицельно бьёт в phase2 (wrap-around reclaim), а не только в phase1.

    6 no-duty заявок, слотов на тик — 4:
      * Тик 1: forward-scan (phase1) забирает РОВНО 4 (== slots) → ветка
        `if len(phase1) < slots` не входит, phase2 не запускается вовсе.
        Заявки 001-004 получают cooldown до t0+15м.
      * Тик 2, now = t0+16м (cooldown 001-004 УЖЕ истёк): курсор после 004 →
        forward-scan видит только 005,006 (2 < slots=4) → phase2 ОБЯЗАН
        добрать недостающие 2 слота через wrap-around, реклеймя остывшие
        001,002 (условие `cooldown_until > now` теперь ложно для них).

    Если бы cooldown-skip в phase2 был сломан «навечно» (например, считал
    остывшую заявку всё ещё в cooldown независимо от `now`), 001-004 не
    попали бы в `taken` во втором тике вовсе. Заметьте: `_prune_expired`
    вызывается В НАЧАЛЕ каждого тика и стирает из `_retry_after` любую
    запись с истёкшим cooldown (тем же условием `v > now`, что и wrap-around
    skip) — так что НЕреклеймленные 003/004 к концу тика 2 просто ОТСУТСТВУЮТ
    в словаре (пруннуты, не переобработаны), а реклеймленные 001/002
    ПРИСУТСТВУЮТ с меткой, равной `now` именно ВТОРОГО тика. Проверяем это
    напрямую, а не «ключ остался с тика 1» (после prune это невозможно в
    принципе — сравнение с tick1-значением тут ничего не докажет)."""
    db, TestSessionLocal = env
    _always_active_config(db, max_requests_per_run=4)

    numbers = [f"260723-{i:03d}" for i in range(1, 7)]
    for i, number in enumerate(numbers):
        _group_request(db, number, specialization="obscure_spec",
                       created_at=FIXED_NOW + timedelta(seconds=i))
    # Ни одного исполнителя со специализацией "obscure_spec" — все 6 всегда no-duty.

    current = {"now": FIXED_NOW}
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: current["now"])

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)

    await orchestrator.run_once()
    # Тик 1: phase1 забирает ровно 4 (== slots) → phase2 не активируется.
    assert set(orchestrator._retry_after.keys()) == set(numbers[:4])
    tick1_retry = dict(orchestrator._retry_after)

    # >15 мин спустя — cooldown первых 4 истёк.
    current["now"] = FIXED_NOW + timedelta(minutes=16)
    await orchestrator.run_once()

    # 005,006 взяты forward-scan'ом; недостающие 2 слота (ровно `remaining`)
    # ОБЯЗАНЫ прийти из phase2-реклейма уже остывших 001-004. `_prune_expired`
    # уже стёр 001-004 из словаря к этому моменту (их cooldown истёк) — значит
    # РЕКЛЕЙМЛЕННЫЕ (и только они) обязаны СНОВА появиться в словаре с
    # НОВОЙ меткой (now второго тика). Если бы phase2 не реклеймила ни одной
    # (сломанный cooldown-skip), reclaimed был бы пуст.
    reclaimed = [n for n in numbers[:4] if n in orchestrator._retry_after]
    assert len(reclaimed) == 2
    for n in reclaimed:
        assert orchestrator._retry_after[n] == current["now"] + timedelta(minutes=15)
        assert orchestrator._retry_after[n] != tick1_retry[n]  # реально обновлена, не осталась старой
    # Оставшиеся 2 из 001-004 не были реклеймлены в этом тике (не хватило
    # `remaining`) — их prune уже стёр, и они НЕ переобрабатывались.
    untouched = [n for n in numbers[:4] if n not in orchestrator._retry_after]
    assert len(untouched) == 2

    # ── Тик 3: курсор РЕГРЕССИРОВАЛ (после тика 2 он указывает на один из
    # реклеймленных 001/002, а НЕ на 006 — последнюю по keyset заявку). Это
    # ключевой regression-сценарий бага: phase1 forward-scan тика 3 резюмирует
    # именно с этой более РАННЕЙ позиции и повторно проходит регион между
    # новым (регрессировавшим) курсором и тем местом, где phase1 был раньше —
    # включая заявки, которые остывают ПРЯМО СЕЙЧАС (005/006, получившие
    # cooldown ещё в тик 2). Без cooldown-проверки в phase1 (старый баг) эти
    # заявки были бы переобработаны заново, несмотря на активный cooldown.
    tick2_retry = dict(orchestrator._retry_after)  # снимок ПОСЛЕ тика 2
    assert set(tick2_retry.keys()) == {"260723-001", "260723-002", "260723-005", "260723-006"}

    # +1 минута после тика 2 (now=t0+16м) → now=t0+17м. Cooldown тика 2 истекает
    # в t0+16+15=t0+31м — на тике 3 у 001/002/005/006 остаётся ЕЩЁ 14 минут до
    # истечения (число специально мирроит эмпирическую проверку ревьюера).
    current["now"] = FIXED_NOW + timedelta(minutes=17)
    await orchestrator.run_once()

    # Все 4 заявки, остывающие с тика 2, ОБЯЗАНЫ остаться нетронутыми —
    # cooldown-метка идентична снимку ПЕРЕД тиком 3 (не обновлена под now
    # тика 3), несмотря на регрессировавший курсор.
    for n in ("260723-001", "260723-002", "260723-005", "260723-006"):
        assert orchestrator._retry_after[n] == tick2_retry[n], (
            f"{n} был переобработан раньше истечения cooldown "
            f"(cursor regression bug): {orchestrator._retry_after[n]} != {tick2_retry[n]}"
        )

    # 003/004 не в cooldown (пруннуты ещё в тике 2, никогда не реклеймлены) —
    # forward-scan тика 3 ЗАКОННО их подхватывает и ставит им СВЕЖИЙ cooldown
    # от now тика 3 (t0+17+15=t0+32м), доказывая, что тест не просто "ничего
    # не изменилось", а именно cooldown-заявки защищены избирательно.
    for n in ("260723-003", "260723-004"):
        assert orchestrator._retry_after[n] == current["now"] + timedelta(minutes=15)


# ─────────────────────────── slot split: both queues same tick ───────────────────────────

@pytest.mark.asyncio
async def test_run_once_splits_slots_between_main_and_residual_same_tick(env, monkeypatch):
    """Обе очереди с backlog'ом В ОДНОМ тике — `max(1, limit // 4)`
    residual-резерв должен реально прорезаться в раздельную обработку обеих
    очередей в рамках ОДНОГО `run_once`, а не только тестироваться «по одной
    очереди за раз» (как во всех остальных тестах модуля)."""
    db, TestSessionLocal = env
    # limit=8 → residual_slots=max(1, 8//4)=2, main_slots=8-2=6.
    _always_active_config(db, max_requests_per_run=8)
    monkeypatch.setattr(orch_mod, "_now_utc", lambda: FIXED_NOW)

    _manager(db, 2, 2002)
    # Ни одного исполнителя вовсе — обе очереди гарантированно «no duty»,
    # что делает подсчёт обработанных заявок детерминированным (никакого
    # реального назначения, только cooldown-запись + уведомление).
    main_numbers = [f"260723-{300 + i:03d}" for i in range(1, 11)]  # 10 > 6 main_slots
    for i, number in enumerate(main_numbers):
        _group_request(db, number, created_at=FIXED_NOW + timedelta(seconds=i))

    residual_numbers = [f"260723-{400 + i:03d}" for i in range(1, 11)]  # 10 > 2 residual_slots
    for i, number in enumerate(residual_numbers):
        _residual_request(db, number, created_at=FIXED_NOW + timedelta(seconds=i))

    fake_bot = FakeBot()
    orchestrator = AutoManagerOrchestrator(bot=fake_bot)
    await orchestrator.run_once()

    processed_main = [n for n in main_numbers if n in orchestrator._retry_after]
    processed_residual = [n for n in residual_numbers if n in orchestrator._retry_after]

    # Не просто счётчики — конкретно ПЕРВЫЕ по keyset заявки каждой очереди
    # (forward-scan с нуля, курсор ещё не двигался).
    assert processed_main == main_numbers[:6]
    assert processed_residual == residual_numbers[:2]
    assert len(orchestrator._retry_after) == 8

    # Ровно одно уведомление на заявку (dedup по request_number) — 6+2=8, не
    # 10+10 (остальные не должны были попасть в тик вовсе).
    assert len(fake_bot.sent) == 8
