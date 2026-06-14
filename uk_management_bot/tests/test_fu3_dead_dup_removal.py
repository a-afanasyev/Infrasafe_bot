"""PRAC-01-FU3 regression: the two F811 dead-duplicate functions removed.

Both were latent bugs masked by Python/aiogram "last/first wins" semantics:

* ``shift_management.handle_template_management`` — TWO module-level handlers,
  both decorated ``@router.callback_query(F.data == "template_management")``.
  aiogram dispatches the FIRST-registered (the full menu impl); the second was
  an obsolete "under development" stub that never ran. Removing the stub must
  leave EXACTLY ONE handler bound to that callback.
* ``UserVerificationService.get_user_documents`` — TWO defs in one class; the
  LAST wins in the class body, so the first was dead. Removing it must not
  change the surviving behaviour (return docs; ``[]`` on error).
"""
from unittest.mock import MagicMock

import pytest
from aiogram.types import CallbackQuery

from uk_management_bot.handlers.shift_management import router as shift_router
from uk_management_bot.services.user_verification_service import UserVerificationService


async def _matching_handlers(router, data: str) -> list:
    cb = CallbackQuery.model_construct(id="1", data=data, chat_instance="x")
    names = []
    for handler in router.callback_query.handlers:
        try:
            ok, _ = await handler.check(cb)
        except Exception:
            ok = False
        if ok:
            names.append(handler.callback.__name__)
    return names


# --- handle_template_management: exactly one handler after dedup -------------
@pytest.mark.asyncio
async def test_template_management_has_single_handler():
    matches = await _matching_handlers(shift_router, "template_management")
    assert matches == ["handle_template_management"], (
        "expected exactly one handler bound to 'template_management' "
        f"(a re-introduced duplicate would reappear here); got {matches}"
    )


# --- get_user_documents: surviving impl behaves correctly --------------------
def test_get_user_documents_returns_query_result():
    db = MagicMock()
    sentinel = [MagicMock(), MagicMock()]
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = sentinel

    svc = UserVerificationService(db)
    assert svc.get_user_documents(user_id=1) == sentinel


def test_get_user_documents_returns_empty_on_error():
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")

    svc = UserVerificationService(db)
    assert svc.get_user_documents(user_id=1) == []
