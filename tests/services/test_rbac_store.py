"""Права с учётом админки ролей: переопределения, свои роли, суперадмин.

Ядро (`authz/store.resolve`) — чистая функция от каталога и снимка таблиц,
поэтому проверяется без базы. Проверки `can`/гейтов идут через подменённый
снимок — так тест видит ровно то, что увидит процесс после чтения таблиц.
"""
import json
from types import SimpleNamespace

import pytest

from uk_management_bot.authz import can, get_action, has_action_roles, store
from uk_management_bot.authz.policy import is_superadmin


def _snap(overrides=None, roles=()):
    return store.Snapshot(version=7, overrides=dict(overrides or {}), roles=frozenset(roles))


@pytest.fixture
def snapshot(monkeypatch):
    """Подменить состояние прав, которое видят проверки."""
    holder = {"snap": None}
    monkeypatch.setattr(store, "current_snapshot", lambda: holder["snap"])
    store.reset_for_tests()

    def _set(snap):
        holder["snap"] = snap

    yield _set
    store.reset_for_tests()


def _user(roles, status="approved", telegram_id=1):
    return SimpleNamespace(roles=json.dumps(roles), status=status, telegram_id=telegram_id, deleted_at=None)


# ── чистое ядро ─────────────────────────────────────────────────────────

def test_no_snapshot_means_catalog_defaults():
    action = get_action("staff.manage")
    assert store.resolve(action, None) == action.default_roles


def test_empty_tables_keep_catalog_defaults():
    action = get_action("requests.execute")
    assert store.resolve(action, _snap(roles={"manager", "executor"})) == action.default_roles


def test_override_grants_and_revokes():
    action = get_action("staff.manage")
    snap = _snap({("executor", "staff.manage"): True, ("manager", "staff.manage"): False},
                 roles={"manager", "executor"})
    assert store.resolve(action, snap) == {"executor"}


def test_custom_role_gets_only_explicit_grants():
    snap = _snap({("senior_exec", "requests.execute"): True}, roles={"senior_exec"})
    assert "senior_exec" in store.resolve(get_action("requests.execute"), snap)
    assert "senior_exec" not in store.resolve(get_action("staff.manage"), snap)


def test_superadmin_only_action_never_goes_to_roles():
    snap = _snap({("manager", "rbac.manage"): True}, roles={"manager"})
    assert store.resolve(get_action("rbac.manage"), snap) == frozenset()


# ── проверки видят переопределения ──────────────────────────────────────

def test_can_follows_override(snapshot):
    assert not can(["executor"], "staff.manage")
    snapshot(_snap({("executor", "staff.manage"): True}, roles={"executor"}))
    assert can(["executor"], "staff.manage")
    assert has_action_roles(["executor"], "staff.manage")


def test_revoked_default_denies(snapshot):
    snapshot(_snap({("manager", "requests.stats"): False}, roles={"manager"}))
    assert not can(["manager"], "requests.stats")


def test_bot_action_gate_reads_rights_per_update(snapshot):
    import asyncio

    from uk_management_bot.handlers._role_gate import ActionGate

    gate = ActionGate("admin_panel.use")
    event = SimpleNamespace()
    assert not asyncio.run(gate(event, roles=["executor"], user=None))
    snapshot(_snap({("executor", "admin_panel.use"): True}, roles={"executor"}))
    assert asyncio.run(gate(event, roles=["executor"], user=None))


# ── кэш и сбои чтения ──────────────────────────────────────────────────

@pytest.fixture
def loader(monkeypatch):
    """Подменить чтение базы: очередь ответов (снимок / None / исключение)."""
    answers: list = []

    def _fake_load(current):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise store._ReadError(str(answer))
        return answer

    monkeypatch.setattr(store, "_load", _fake_load)
    store.reset_for_tests()
    yield answers
    store.reset_for_tests()


def test_read_error_keeps_last_known_rights(loader):
    """Снятое в админке право не возвращается из-за сбоя чтения базы."""
    revoked = _snap({("manager", "requests.stats"): False}, roles={"manager"})
    loader.extend([revoked, RuntimeError("pool timeout")])
    assert not can(["manager"], "requests.stats")
    store.invalidate()
    store.current_snapshot()
    store.wait_for_refresh()
    assert not loader, "фоновое обновление должно было сходить в базу"
    assert store.current_snapshot() is revoked
    assert not can(["manager"], "requests.stats")


def test_read_error_before_first_load_means_catalog(loader):
    loader.append(RuntimeError("db down"))
    assert store.current_snapshot() is None
    assert can(["manager"], "requests.stats")


def test_invalidate_rereads_without_dropping_state(loader):
    first = _snap(roles={"manager"})
    second = store.Snapshot(version=8, overrides={("manager", "requests.stats"): False},
                            roles=frozenset({"manager"}))
    loader.extend([first, second])
    assert store.current_snapshot() is first
    store.invalidate()
    assert store.current_snapshot() is first  # отдаётся сразу, читается в фоне
    store.wait_for_refresh()
    assert store.current_snapshot() is second
    assert not can(["manager"], "requests.stats")


def test_slow_database_does_not_block_checks(monkeypatch):
    """После первого чтения проверка прав не ждёт базу — сверка идёт в фоне."""
    import threading

    gate, started = threading.Event(), threading.Event()
    calls = []

    def _slow_load(current):
        calls.append(current)
        if len(calls) > 1:
            started.set()
            gate.wait(5)
        return _snap(roles={"manager"})

    monkeypatch.setattr(store, "_load", _slow_load)
    store.reset_for_tests()
    try:
        first = store.current_snapshot()
        store.invalidate()
        assert store.current_snapshot() is first  # фоновый поток висит, ответ — сразу
        assert can(["manager"], "requests.stats")
        assert started.wait(2) and len(calls) == 2  # сверка идёт, но в фоне
    finally:
        gate.set()
        store.reset_for_tests()


def test_access_service_can_read_rbac_tables():
    """Каждая таблица, которую читает store, выдана охране (access_app_rw) в 024.

    Иначе access-api под `uk_access_runtime` получает permission denied и
    молча остаётся на правах из каталога.
    """
    import importlib.util
    from pathlib import Path

    from uk_management_bot.database.models.rbac import RbacRole, RbacRolePermission, RbacState

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0024_rbac_access_read.py"
    spec = importlib.util.spec_from_file_location("m0024", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    read_by_store = {m.__tablename__ for m in (RbacRole, RbacRolePermission, RbacState)}
    assert read_by_store <= set(module.RBAC_TABLES)


def test_cache_lives_in_its_snapshot():
    """Посчитанное по старому снимку не попадает в кэш нового."""
    action = get_action("requests.stats")
    old, new = _snap(roles={"manager"}), _snap({("manager", "requests.stats"): False}, roles={"manager"})
    old.cache[action.key] = store.resolve(action, old)
    assert action.key not in new.cache


# ── суперадмин ──────────────────────────────────────────────────────────

@pytest.fixture
def admin_ids(monkeypatch):
    from uk_management_bot.config.settings import settings

    monkeypatch.setattr(settings, "ADMIN_USER_IDS", [555])


def test_superadmin_is_env_listed_and_active(admin_ids):
    assert is_superadmin(_user(["applicant"], telegram_id=555))
    assert not is_superadmin(_user(["manager"], telegram_id=556))
    assert not is_superadmin(_user(["manager"], status="blocked", telegram_id=555))


def test_only_superadmin_can_manage_rbac(admin_ids):
    assert can(_user(["applicant"], telegram_id=555), "rbac.manage")
    assert can(_user(["applicant"], telegram_id=555), "rbac.view")
    assert not can(_user(["manager"], telegram_id=556), "rbac.manage")
    assert can(_user(["manager"], telegram_id=556), "rbac.view")


def test_superadmin_gets_no_extra_business_rights(admin_ids):
    """Суперадмин настраивает права, но сам по себе заявками не управляет."""
    assert not can(_user(["applicant"], telegram_id=555), "requests.manage")
