"""ARCH-013 — the ``session_scope()`` invariant.

``get_db()`` is a sync generator; calling only ``next()`` on it never runs the
generator's ``finally: db.close()`` deterministically, so handlers that did
``db = next(get_db())`` and returned/raised before exhausting the generator
leaked the connection until GC. ``session_scope()`` is the close-only context
manager that replaces that idiom — these tests pin the one property that makes
it safe: ``db.close()`` runs no matter how the block exits, including on a raise.
"""
from unittest.mock import MagicMock, patch

import pytest

from uk_management_bot.database import session as session_module


def test_session_scope_closes_on_normal_exit():
    """Happy path: the yielded session is closed once when the block ends."""
    fake_db = MagicMock()
    with patch.object(session_module, "SessionLocal", return_value=fake_db):
        with session_module.session_scope() as db:
            assert db is fake_db
            fake_db.close.assert_not_called()  # still open inside the block
    fake_db.close.assert_called_once()


def test_session_scope_closes_on_exception():
    """Leak invariant: a raise inside the block still closes the session, and
    the exception propagates unchanged."""
    fake_db = MagicMock()
    with patch.object(session_module, "SessionLocal", return_value=fake_db):
        with pytest.raises(ValueError, match="boom"):
            with session_module.session_scope() as db:
                assert db is fake_db
                raise ValueError("boom")
    fake_db.close.assert_called_once()


def test_session_scope_closes_on_early_return():
    """A function that returns from inside the block still closes the session."""
    fake_db = MagicMock()

    def handler():
        with patch.object(session_module, "SessionLocal", return_value=fake_db):
            with session_module.session_scope() as db:
                return db  # early return out of the with-block

    handler()
    fake_db.close.assert_called_once()
