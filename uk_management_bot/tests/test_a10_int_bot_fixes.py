"""Пин-тесты этапа 2 аудита #10 (ревью внутренней защиты, 2026-10-24) — бот.

A10-INT-01 — модерация привилегированной цели из бота отказывается в AuthService;
A10-INT-02 — ключи локалей жителя/исполнителя не несут текст исключения;
A10-INT-05 — финалы FSM модерации перепроверяют право.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message, User as TgUser

_PRIV = "uk_management_bot.services.users.privileged"
_LOCALES = Path(__file__).resolve().parents[1] / "config" / "locales"


def _user(roles: str, user_id: int = 7) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.telegram_id = 900_000_000 + user_id  # не из ADMIN_USER_IDS
    user.roles = roles
    user.status = "approved"
    return user


# ── A10-INT-01 ───────────────────────────────────────────────────────


def test_privileged_target_predicate():
    from uk_management_bot.services.users.privileged import is_privileged_target

    assert is_privileged_target(_user('["manager"]')) is True
    assert is_privileged_target(_user('["executor", "admin"]')) is True
    assert is_privileged_target(_user('["executor"]')) is False
    with patch(f"{_PRIV}.is_listed_superadmin", return_value=True):
        assert is_privileged_target(_user('["applicant"]')) is True


def _db_returning(user: MagicMock) -> MagicMock:
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.first.return_value = user
    chain.with_for_update.return_value.first.return_value = user
    return db


@pytest.mark.parametrize("method, args", [
    ("block_user", (1, "spam")),
    ("unblock_user", (1, "ok")),
    ("assign_role", ("executor", 1, "c")),
    ("remove_role", ("manager", 1, "c")),
])
def test_auth_service_refuses_moderation_of_privileged_target(method, args):
    from uk_management_bot.services.auth_service import AuthService

    target = _user('["manager"]')
    target.status = "blocked" if method == "unblock_user" else "approved"
    db = _db_returning(target)

    assert getattr(AuthService(db), method)(target.id, *args) is False
    db.commit.assert_not_called()
    assert target.status in ("approved", "blocked")  # не менялся
    assert target.roles == '["manager"]'


def test_auth_service_refuses_deletion_of_privileged_target():
    from uk_management_bot.services.auth_service import AuthService

    target = _user('["manager"]')
    db = _db_returning(target)

    outcome = AuthService(db).delete_user_purging_documents(target.id, 1, "bye")

    assert outcome.ok is False
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_auth_service_still_blocks_ordinary_executor():
    """Гейт не задевает рядовых: исполнитель блокируется как раньше."""
    from uk_management_bot.services.auth_service import AuthService

    target = _user('["executor"]')
    db = _db_returning(target)
    db.execute.return_value.scalar.return_value = "2026-10-24"

    assert AuthService(db).block_user(target.id, 1, "spam") is True
    assert target.status == "blocked"
    db.commit.assert_called_once()


# ── A10-INT-02 ───────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", ["ru", "uz"])
def test_user_facing_error_keys_do_not_carry_exception_text(locale):
    data = json.loads((_LOCALES / f"{locale}.json").read_text(encoding="utf-8"))
    for path in (
        "common.error_occurred",
        "request_reports.handlers.error_occurred",
        "request_status_mgmt.handlers.error_occurred",
    ):
        node = data
        for key in path.split("."):
            node = node[key]
        assert "{error}" not in node, f"{locale}:{path} отдаёт str(e) жителю/исполнителю"


# ── A10-INT-05 ───────────────────────────────────────────────────────


def _msg() -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = 1
    msg.text = "причина"
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [
    "process_approval_comment", "process_block_reason",
    "process_unblock_comment", "process_delete_reason",
])
async def test_fsm_moderation_finals_regate_permission(handler):
    from uk_management_bot.handlers.user_management import fsm

    msg = _msg()
    state = AsyncMock()
    run_db = AsyncMock()
    with patch.object(fsm, "run_db", run_db), patch.object(
        fsm, "get_text", side_effect=lambda key, language="ru": key
    ):
        await getattr(fsm, handler)(msg, state, roles=["applicant"], user=None)

    run_db.assert_not_awaited()
    state.clear.assert_awaited_once()
    assert msg.answer.call_args.args[0] == "errors.permission_denied"
