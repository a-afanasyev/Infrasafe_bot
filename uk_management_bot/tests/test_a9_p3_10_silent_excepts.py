"""A9-P3-10: «немые» except бота больше не глотают ошибку без следа.

Поведение (фолбэк) сохраняется — меняется только то, что сбой виден в логе:
ошибка БД при чтении ролей больше не неотличима от «пользователь не найден»,
ошибка чтения языка для отказа в доступе — тоже.
"""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_load_roles_fallback_logs_db_error(caplog):
    from uk_management_bot.handlers.base import _load_roles_fallback

    db = MagicMock()
    db.query.side_effect = RuntimeError("db is down")

    with caplog.at_level(logging.WARNING, logger="uk_management_bot.handlers.base"):
        assert _load_roles_fallback(db, 777) is None  # фолбэк прежний

    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("777" in m and "db is down" in m for m in msgs), msgs


def test_load_roles_fallback_user_not_found_is_silent(caplog):
    from uk_management_bot.handlers.base import _load_roles_fallback

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with caplog.at_level(logging.WARNING, logger="uk_management_bot.handlers.base"):
        assert _load_roles_fallback(db, 778) is None

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_require_role_logs_language_lookup_error(caplog):
    from uk_management_bot.middlewares.auth import require_role

    called = []

    @require_role(["manager"])
    async def handler(event, **kwargs):
        called.append(True)

    event = SimpleNamespace(from_user=SimpleNamespace(id=4242, language_code=None))

    with patch(
        "uk_management_bot.utils.helpers.get_user_language",
        side_effect=RuntimeError("lang read failed"),
    ), caplog.at_level(logging.WARNING, logger="uk_management_bot.middlewares.auth"):
        result = await handler(event, roles=["applicant"], db=MagicMock())

    assert result is None and not called  # отказ в доступе, как и был
    msgs = [r.getMessage() for r in caplog.records]
    assert any("4242" in m and "lang read failed" in m for m in msgs), msgs
