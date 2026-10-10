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
    store.invalidate()

    def _set(snap):
        holder["snap"] = snap
        store._effective_cache.clear()

    yield _set
    store.invalidate()


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
