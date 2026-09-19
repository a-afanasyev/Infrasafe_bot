"""AUD8-SEC-02: rate-limit на резидентские write-действия (заявки на ТС, пропуска).

Раньше POST /requests и POST /passes у applicant'а не ограничивались: один аккаунт
мог за минуту завести тысячи pending-заявок (очередь менеджера) или гостевых
кодов. Лимит — per-user фиксированное окно (INCR+EX в Redis / in-memory в тестах)
на том же стор-бэкенде, что lockout одноразовых кодов (`code_rate_limit`):
fail-closed в проде, никакой тихой деградации. Считаются ПОПЫТКИ (в том числе
отклонённые 403) — иначе перебор чужих apartment_id был бы бесплатным.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, status

from access_control.services.code_rate_limit import FailureCounterStore

RESIDENT_WRITE_LIMIT = int(os.getenv("ACCESS_RESIDENT_WRITE_LIMIT", "30"))
RESIDENT_WRITE_WINDOW_SECONDS = int(os.getenv("ACCESS_RESIDENT_WRITE_WINDOW_SECONDS", "3600"))


def enforce_resident_write_limit(
    store: FailureCounterStore, *, user_id: int, action: str
) -> None:
    """Зафиксировать попытку и отбить 429 сверх лимита в окне (Retry-After = окно)."""
    window = RESIDENT_WRITE_WINDOW_SECONDS
    count = store.record_failure(f"resident:{action}:{user_id}", window)
    if count > RESIDENT_WRITE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "too_many_requests"},
            headers={"Retry-After": str(window)},
        )
